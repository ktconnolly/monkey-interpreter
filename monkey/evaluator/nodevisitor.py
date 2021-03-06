from object.environment import Environment
from object.object import (
    ObjectType,
    Integer,
    ReturnValue,
    Function,
    Error,
    String,
    BuiltIn,
    Array,
    NULL,
    TRUE,
    FALSE,
    Hashable,
    HashPair,
    Hash,
)
from .builtin import BUILTIN


class NodeVisitor:
    def visit(self, node, env):
        method_name = "visit_" + type(node).__name__
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node, env)

    def generic_visit(self, node, env):
        raise Exception("No visit_{} method".format(type(node).__name__))

    def visit_ExpressionStatement(self, node, env):
        return self.visit(node.expression, env)

    def visit_IntegerLiteral(self, node, _):
        return Integer(node.value)

    def visit_BooleanLiteral(self, node, _):
        return TRUE if node.value else FALSE

    def visit_LetStatement(self, node, env):
        val = self.visit(node.value, env)
        if is_error(val):
            return val

        env.set(node.name.value, val)

    def visit_FunctionLiteral(self, node, env):
        return Function(node.params, node.body, env)

    def visit_StringLiteral(self, node, _):
        return String(node.value)

    def visit_CallExpression(self, node, env):
        function = self.visit(node.function, env)
        if is_error(function):
            return function

        args = self.eval_expressions(node.args, env)

        if len(args) == 1 and is_error(args[0]):
            return args[0]

        return self.apply_function(function, args)

    def visit_PrefixExpression(self, node, env):
        right = self.visit(node.right, env)
        if is_error(right):
            return right

        return eval_prefix_expression(node.operator, right)

    def visit_InfixExpression(self, node, env):
        left = self.visit(node.left, env)
        if is_error(left):
            return left

        right = self.visit(node.right, env)
        if is_error(right):
            return right

        if isinstance(left, Integer) and isinstance(right, Integer):
            return eval_integer_infix_expression(node.operator, left, right)
        elif isinstance(left, String) and isinstance(right, String):
            return eval_string_infix_expression(node.operator, left, right)
        elif node.operator == "==":
            return to_bool(left.value == right.value)
        elif node.operator == "!=":
            return to_bool(left.value != right.value)
        elif left.type() != right.type():
            return Error(
                f"type mismatch: {left.type().value} {node.operator} {right.type().value}"
            )
        else:
            return Error(
                f"unknown operator: {left.type().value} {node.operator} {right.type().value}"
            )

    def visit_BlockStatement(self, node, env):
        result = None
        for stmt in node.statements:
            result = self.visit(stmt, env)

            if result is not None:
                rt = result.type()
                if rt in (ObjectType.RETURN_VALUE, ObjectType.ERROR):
                    return result

        return result

    def visit_Identifier(self, node, env):
        val = env.get(node.value)
        if val is not None:
            return val

        val = BUILTIN.get(node.value)
        if val is not None:
            return val

        return Error(f"identifier not found: {node.value}")

    def visit_IfExpression(self, node, env):
        condition = self.visit(node.condition, env)
        if is_error(condition):
            return condition

        if is_truthy(condition):
            return self.visit(node.consequence, env)
        elif node.alternative is not None:
            return self.visit(node.alternative, env)
        else:
            return NULL

    def visit_WhileExpression(self, node, env):
        while True:
            condition = self.visit(node.condition, env)
            if is_error(condition):
                return condition

            if not is_truthy(condition):
                return None

            consequence = self.visit(node.consequence, env)
            if is_error(consequence):
                return consequence

    def visit_ReturnStatement(self, node, env):
        val = self.visit(node.return_value, env)
        return val if is_error(val) else ReturnValue(val)

    def visit_ArrayLiteral(self, node, env):
        elements = self.eval_expressions(node.elements, env)
        if len(elements) == 1 and is_error(elements[0]):
            return elements[0]

        return Array(elements)

    def visit_IndexExpression(self, node, env):
        left = self.visit(node.left, env)
        if is_error(left):
            return left

        index = self.visit(node.index, env)
        if is_error(index):
            return index

        return eval_index_expression(left, index)

    def visit_HashLiteral(self, node, env):
        pairs = {}

        for key_node, val_node in node.pairs.items():
            key = self.visit(key_node, env)
            if is_error(key):
                return key

            if not isinstance(key, Hashable):
                return Error(f"unusable as hash key: {key.type().value}")

            value = self.visit(val_node, env)
            if is_error(value):
                return value

            hashed_key = key.hash_key()
            pairs[hashed_key] = HashPair(key, value)

        return Hash(pairs)

    def eval_expressions(self, exps, env):
        result = []
        for e in exps:
            evaluated = self.visit(e, env)
            if is_error(evaluated):
                return [evaluated]

            result.append(evaluated)

        return result

    def apply_function(self, fn, args):
        if isinstance(fn, Function):
            extended_env = extend_function_env(fn, args)
            if isinstance(extended_env, Error):
                return extended_env

            evaluated = self.visit(fn.body, extended_env)
            if evaluated is None:
                return None

            return unwrap_return_value(evaluated)

        elif isinstance(fn, BuiltIn):
            return fn.function(args)
        else:
            return Error(f"not a function: {fn}")


def evaluate(program, env):
    evaluator = NodeVisitor()

    result = None
    for stmt in program.statements:
        result = evaluator.visit(stmt, env)

        if isinstance(result, ReturnValue):
            return result.value
        elif isinstance(result, Error):
            return result

    return result


def eval_bang_operator_expression(right):
    return to_bool(right in (FALSE, NULL))


def eval_minus_prefix_operator_expression(right):
    if not isinstance(right, Integer):
        return Error(f"unknown operator: -{right.type().value}")
    return Integer(-right.value)


def eval_string_infix_expression(operator, left, right):
    if operator != "+":
        return Error(
            f"unknown operator: {left.type().value} {operator} {right.type().value}"
        )
    return String(left.value + right.value)


def eval_index_expression(left, index):
    if isinstance(left, Array) and isinstance(index, Integer):
        return eval_array_index_expression(left, index)
    elif isinstance(left, Hash):
        return eval_hash_index_expression(left, index)
    else:
        return Error(f"index operator not supported {left.type().value}")


def eval_array_index_expression(array, index):
    if index.value < 0 or index.value >= len(array.elements):
        return NULL
    return array.elements[index.value]


def eval_hash_index_expression(hash_obj, index):
    if not isinstance(index, Hashable):
        return Error(f"unusable as hash key: {index.type().value}")

    pair = hash_obj.pairs.get(index.hash_key())
    return pair.value if pair is not None else NULL


def eval_integer_infix_expression(operator, left, right):
    left_val = left.value
    right_val = right.value

    if operator == "+":
        return Integer(left_val + right_val)
    elif operator == "-":
        return Integer(left_val - right_val)
    elif operator == "*":
        return Integer(left_val * right_val)
    elif operator == "/":
        return Integer(left_val / right_val)
    elif operator == "<":
        return to_bool(left_val < right_val)
    elif operator == ">":
        return to_bool(left_val > right_val)
    elif operator == "==":
        return to_bool(left_val == right_val)
    elif operator == "!=":
        return to_bool(left_val != right_val)
    else:
        return Error(
            f"unknown operator: {left.type().value} {operator} {right.type().value}"
        )


def eval_prefix_expression(operator, right):
    if operator == "!":
        return eval_bang_operator_expression(right)
    elif operator == "-":
        return eval_minus_prefix_operator_expression(right)
    else:
        return Error(f"unknown operator: {operator}{right.type().value}")


def extend_function_env(fn, args):
    env = Environment(fn.env)
    for i, param in enumerate(fn.params):
        env.set(param.value, args[i])
    return env


def unwrap_return_value(obj):
    return obj.value if isinstance(obj, ReturnValue) else obj


def is_truthy(obj):
    return obj not in (NULL, FALSE)


def is_error(obj):
    return obj is not None and isinstance(obj, Error)


def to_bool(value):
    return TRUE if value is True else FALSE
