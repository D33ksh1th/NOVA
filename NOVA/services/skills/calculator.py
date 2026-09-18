"""
Calculator Skill

Evaluates mathematical expressions safely using Python's
ast module — no eval(), no LLM needed.

Handles:
  - Arithmetic:   25 * 90,  (100 + 50) / 3,  2 ** 10
  - Unit queries: "what is 5 km in miles?" → delegated to LLM
  - Clear trigger: message contains only digits + operators
"""

import ast
import operator
import re
from typing import Union

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


# Safe operators
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

_EXPR_RE = re.compile(
    r"[\d\s\+\-\*\/\^\(\)\.\%]+",
)

_TRIGGER_RE = re.compile(
    r"(calculate|compute|what is|how much is|evaluate|solve)\s+([\d\s\+\-\*\/\^\(\)\.\%]+)",
    re.IGNORECASE,
)

_BARE_EXPR_RE = re.compile(
    r"^[\d\s\+\-\*\/\^\(\)\.\%]+$"
)


def _safe_eval(expr: str) -> Union[float, int]:
    """Evaluate a math expression without using eval()."""
    # Replace ^ with ** for power
    expr = expr.replace("^", "**")
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body)


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    if isinstance(node, ast.BinOp):
        op_fn = _OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {node.op}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return op_fn(left, right)
    if isinstance(node, ast.UnaryOp):
        op_fn = _OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {node.op}")
        return op_fn(_eval_node(node.operand))
    raise ValueError(f"Unsupported node type: {type(node)}")


class CalculatorSkill(Skill):

    @property
    def name(self) -> str:
        return "calculator"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.CALCULATION:
            return True
        text = ctx.message.strip()
        # Bare expression like "25 * 90" or "(100+50)/3"
        if _BARE_EXPR_RE.match(text):
            return True
        # Triggered with a keyword
        if _TRIGGER_RE.search(text):
            return True
        return False

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("CalculatorSkill executing")
        text = ctx.message.strip()

        # Extract expression
        match = _TRIGGER_RE.search(text)
        if match:
            expr = match.group(2).strip()
        else:
            expr = text

        # Clean: remove trailing words after the expression
        # e.g. "calculate 5 * 4 please" → "5 * 4"
        expr = re.sub(r"[^\d\s\+\-\*\/\^\(\)\.\%]", "", expr).strip()

        try:
            result = _safe_eval(expr)
            # Format: integer if whole number
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return {
                "action": "calculator",
                "intent": ctx.intent.value,
                "expression": expr,
                "result": result,
                "response": f"{expr} = {result}",
            }
        except Exception as ex:
            logger.warning(f"CalculatorSkill failed to evaluate {expr!r}: {ex}")
            return {
                "action": "calculator",
                "intent": ctx.intent.value,
                "response": f"I couldn't evaluate that expression. Please check the syntax.",
            }
