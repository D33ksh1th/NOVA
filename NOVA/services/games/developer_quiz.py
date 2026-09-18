"""Local, single-user developer quiz with deterministic scoring and no tool access."""

from __future__ import annotations

import random
import re
from threading import Lock


QUESTIONS = (
    ("Which HTTP status means a resource was created?", ("200", "201", "204"), "b", "201 means Created; 204 means No Content."),
    ("Which SQL construct safely supplies user input to a query?", ("String concatenation", "A parameterized query", "An f-string"), "b", "Bind parameters keep data separate from SQL syntax."),
    ("Which Git command shows unstaged changes?", ("git diff", "git log", "git status --short"), "a", "git diff shows unstaged changes; git status summarizes paths and states."),
    ("What does Python's finally block normally do?", ("Runs only on success", "Retries exceptions", "Runs when leaving the try statement"), "c", "finally performs cleanup on normal exit and exception propagation."),
    ("Which HTTP method is defined as safe and idempotent?", ("POST", "GET", "PATCH"), "b", "GET requests retrieval and should not change server state."),
    ("What prevents two requests from creating the same payment twice?", ("An idempotency key with server-side deduplication", "A longer timeout", "A browser refresh"), "a", "The server must associate the key with an operation and its result."),
    ("Where should an API secret normally live?", ("A committed config file", "Browser JavaScript", "A server-side secret store"), "c", "Keep secrets out of source control and client bundles."),
    ("What is a regression test intended to catch?", ("Only compiler warnings", "Previously working behavior breaking", "Every possible future bug"), "b", "Regression tests check established behavior after a change."),
)


class DeveloperQuiz:
    def __init__(self) -> None:
        self._lock = Lock()
        self._questions = []
        self._index = 0
        self._score = 0

    def handle(self, message: str) -> dict | None:
        text = message.strip()
        text = re.sub(r"^(?:(?:hey|hi|hello)\s+)?(?:nova|lumi)\b[\s,:!]*", "", text, flags=re.I)
        text = re.sub(r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?", "", text, flags=re.I)
        text = text.casefold().rstrip("?.!")
        with self._lock:
            if text == "quiz me" or re.fullmatch(r"(?:(?:let's|let us|i want to) )?(?:play|start) (?:a |the )?(?:fun )?(?:game|(?:developer|coding|code) quiz)", text):
                if self._questions:
                    return self._reply("A quiz is already running. " + self._question(), "RUNNING")
                self._questions = random.sample(QUESTIONS, 5)
                self._index = self._score = 0
                return self._reply("Arcade: five-question developer quiz. Answer A, B or C; say 'stop game' to end.\n" + self._question(), "RUNNING")
            if re.fullmatch(r"(?:stop|cancel|end|quit) (?:the )?(?:game|quiz)", text):
                response = f"Quiz stopped. Score: {self._score}/{self._index} answered." if self._questions else "No quiz is running."
                self._questions = []
                return self._reply(response, "STOPPED")
            if text in {"game status", "quiz status", "repeat question", "quiz help"}:
                if not self._questions:
                    return self._reply("No quiz is running. Say 'play a game' to start a developer quiz.", "IDLE")
                return self._reply(self._question() + "\nAnswer A, B or C, skip question, or stop game.", "RUNNING")
            answer = re.fullmatch(r"(?:(?:quiz answer|answer|option)\s+)?([abc])", text)
            skip = text == "skip question"
            if not self._questions or not (answer or skip):
                return None
            _, options, expected, explanation = self._questions[self._index]
            correct = bool(answer and answer.group(1) == expected)
            self._score += int(correct)
            self._index += 1
            feedback = "Correct." if correct else f"{'Skipped.' if skip else 'Not quite.'} Answer: {expected.upper()}. {options[ord(expected) - ord('a')]}"
            response = f"{feedback} {explanation}\nScore: {self._score}/{self._index}."
            if self._index == len(self._questions):
                self._questions = []
                return self._reply(response + " Quiz complete.", "COMPLETED")
            return self._reply(response + "\n" + self._question(), "RUNNING")

    def _question(self) -> str:
        question, options, _, _ = self._questions[self._index]
        choices = "\n".join(f"{chr(65 + index)}. {option}" for index, option in enumerate(options))
        return f"Question {self._index + 1}/5: {question}\n{choices}"

    def _reply(self, response: str, state: str) -> dict:
        return {"response": response, "intent": "game", "action": "developer_quiz",
                "data": {"game": "developer_quiz", "state": state, "score": self._score,
                         "answered": self._index, "total": 5}}