"""
Task Classifier

Determines what kind of AI task the user is asking for.
"""

from packages.common import logger

from services.models.task import ModelTask


class TaskClassifier:

    def classify(
        self,
        message: str,
    ) -> ModelTask:

        text = message.lower()

        # Reflection / review requests should use the reasoning model.
        if any(
            word in text
            for word in [
                "reflection",
                "reflect",
                "review",
                "verify",
                "critique",
                "improve answer",
            ]
        ):
            logger.info(
                "Task Classified -> REASONING"
            )

            return ModelTask.REASONING

        # -----------------------------
        # Coding
        # -----------------------------

        coding_keywords = [

            "code",
            "python",
            "java",
            "javascript",
            "typescript",
            "c++",
            "c#",
            "fastapi",
            "flask",
            "django",
            "react",
            "angular",
            "node",
            "express",
            "sql",
            "mysql",
            "postgres",
            "mongodb",
            "api",
            "backend",
            "frontend",
            "algorithm",
            "class",
            "function",
            "debug",
            "refactor",
            "bug",
            "program",
        ]

        # -----------------------------
        # Security
        # -----------------------------

        security_keywords = [

            "security",
            "vulnerability",
            "cve",
            "scan",
            "exploit",
            "sql injection",
            "xss",
            "csrf",
            "pentest",
            "owasp",
            "secret",
            "credential",
            "malware",
            "ransomware",
        ]

        # -----------------------------
        # Embeddings
        # -----------------------------

        embedding_keywords = [

            "remember",
            "memory",
            "document",
            "knowledge",
            "search",
            "find",
            "recall",
        ]

        # -----------------------------
        # Classification
        # -----------------------------

        if any(
            word in text
            for word in security_keywords
        ):

            logger.info(
                "Task Classified -> SECURITY"
            )

            return ModelTask.SECURITY

        if any(
            word in text
            for word in coding_keywords
        ):

            logger.info(
                "Task Classified -> CODING"
            )

            return ModelTask.CODING

        if any(
            word in text
            for word in embedding_keywords
        ):

            logger.info(
                "Task Classified -> EMBEDDING"
            )

            return ModelTask.EMBEDDING

        logger.info(
            "Task Classified -> CHAT"
        )

        return ModelTask.CHAT