"""Tests v0.4 : fonctions anonymes et fermetures, Result, match, try/catch, optionnels, @native."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from compiler import driver
from compiler.driver import CompileErrors

pytestmark = pytest.mark.skipif(driver.find_c_compiler() is None, reason="aucun compilateur C")


def run_src(src: str, stdin: str = ""):
    c = driver.compile_to_c(src, "t.air")
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "prog")
        driver.build_binary(c, exe)
        r = subprocess.run([exe], input=stdin, capture_output=True, text=True, timeout=10)
    return r.stdout, r.stderr, r.returncode


def prog(body: str, top: str = "") -> str:
    return top + "\nfun main()\n" + "".join("    " + l + "\n" for l in body.strip().splitlines()) + "end\nmain()\n"


def out(body: str, top: str = "", stdin: str = "") -> str:
    o, e, code = run_src(prog(body, top), stdin)
    assert code == 0, e
    return o


def compile_error(body: str, top: str = "") -> str:
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c(prog(body, top), "t.air")
    return "\n".join(str(e) for e in ei.value.errors)


# ── fonctions anonymes et fermetures ─────────────────────────────────────────

def test_list_higher_order_methods():
    assert out('''
nums = [1, 2, 3, 4, 5]
print(nums.map(fun(x) => x * 2))
print(nums.filter(fun(x) => x % 2 == 0))
print(nums.reduce(0, fun(acc, x) => acc + x))
print(nums.any(fun(x) => x > 4), nums.all(fun(x) => x > 4))
''') == "[2, 4, 6, 8, 10]\n[2, 4]\n15\ntrue false\n"


def test_map_changes_element_type_and_each_runs_in_order():
    assert out('''
words = ["a", "bb", "ccc"]
print(words.map(fun(w) => w.length()))
words.each(fun(w) => print("<{w}>"))
''') == "[1, 2, 3]\n<a>\n<bb>\n<ccc>\n"


def test_closure_captures_by_value_at_creation():
    assert out('''
k = 10
add = fun(x: Int) => x + k
k = 99
print(add(1))
''') == "11\n"


def test_returning_a_closure_and_chained_call():
    top = '''fun make_adder(k: Int) -> Fun[Int, Int]
    return fun(x) => x + k
end'''
    assert out("add3 = make_adder(3)\nprint(add3(4), make_adder(100)(1))", top) == "7 101\n"


def test_named_function_as_value():
    top = '''fun double(n: Int) -> Int
    return n * 2
end
fun apply(f: Fun[Int, Int], x: Int) -> Int
    return f(x)
end'''
    assert out("print(apply(double, 21))\nprint([1, 2].map(double))", top) == "42\n[2, 4]\n"


def test_nested_lambdas_capture_through_both_levels():
    assert out('''
base = 100
outer = fun(a: Int) => [1, 2].map(fun(b) => a + b + base)
print(outer(10))
''') == "[111, 112]\n"


def test_lambda_inside_method_uses_fields_and_self_methods():
    top = '''blueprint Counter
    step: Int = 5
    fun bump(n: Int) -> Int
        return n + step
    end
    fun bump_all(xs: List[Int]) -> List[Int]
        return xs.map(fun(x) => bump(x))
    end
end'''
    assert out("c = Counter.new()\nprint(c.bump_all([1, 2]))", top) == "[6, 7]\n"


def test_lambda_body_int_is_widened_to_expected_float():
    assert out("print(apply(fun(x) => 1, 2.5))",
               "fun apply(f: Fun[Float, Float], x: Float) -> Float\n    return f(x)\nend") == "1.0\n"


def test_arguments_of_a_closure_call_are_evaluated_left_to_right():
    top = '''fun tick(label: String) -> Int
    print(label)
    return 1
end'''
    assert out("f = fun(a: Int, b: Int) => a + b\nprint(f(tick(\"first\"), tick(\"second\")))", top) == "first\nsecond\n2\n"


def test_lambda_param_without_context_is_an_error_with_a_hint():
    msg = compile_error("f = fun(x) => x + 1")
    assert "ne peut pas être déduit" in msg and "fun(x: Int)" in msg


def test_filter_needs_a_bool():
    assert "doit retourner un Bool" in compile_error("print([1, 2].filter(fun(x) => x + 1))")


def test_wrong_lambda_arity():
    assert "paramètre(s)" in compile_error("print([1, 2].map(fun(a, b) => a))")


def test_functions_cannot_be_compared():
    assert "comparer des fonctions" in compile_error("f = fun(x: Int) => x\nprint(f == f)")


def test_calling_a_non_function_is_an_error():
    assert "appeler" in compile_error("x = 3\nprint(x(1))") or "fonction" in compile_error("x = 3\nprint(x(1))")


# ── Result, Ok / Err, ?, match ────────────────────────────────────────────────

DIVIDE = '''fun divide(a: Float, b: Float) -> Result[Float]
    if b == 0.0
        return Err("division par zéro")
    end
    return Ok(a / b)
end'''


def test_result_values_print_like_ok_and_err():
    assert out("print(divide(10.0, 4.0))\nprint(divide(1.0, 0.0))", DIVIDE) == "Ok(2.5)\nErr(division par zéro)\n"


def test_question_mark_returns_the_error_early():
    top = DIVIDE + '''
fun half(a: Float, b: Float) -> Result[Float]
    r = divide(a, b)?
    return Ok(r / 2.0)
end'''
    assert out("print(half(9.0, 3.0))\nprint(half(9.0, 0.0))", top) == "Ok(1.5)\nErr(division par zéro)\n"


def test_question_mark_does_not_run_the_rest_after_an_error():
    top = DIVIDE + '''
fun f(b: Float) -> Result[Float]
    x = divide(1.0, b)?
    print("jamais atteint si b == 0")
    return Ok(x)
end'''
    assert out("print(f(0.0))", top) == "Err(division par zéro)\n"


def test_match_statement_with_ok_err_and_multi_statement_arms():
    assert out('''
match divide(8.0, 2.0)
    Ok(v) =>
        print("ok {v}")
        print("deux lignes")
    Err(m) => print("err {m}")
end
match divide(1.0, 0.0)
    Ok(v) => print("ok {v}")
    Err(m) => print("err {m}")
end
''', DIVIDE) == "ok 4.0\ndeux lignes\nerr division par zéro\n"


def test_match_expression_with_multiline_if_and_wildcard():
    top = '''fun calc(op: String, a: Float, b: Float) -> Result[Float]
    result = match op
        "+" => Ok(a + b)
        "/" => if b == 0.0
            Err("div par zéro")
        else
            Ok(a / b)
        end
        _ => Err("opérateur inconnu : {op}")
    end
    return result
end'''
    assert out('print(calc("+", 1.0, 2.0), calc("/", 1.0, 0.0), calc("?", 1.0, 2.0))', top) == \
        "Ok(3.0) Err(div par zéro) Err(opérateur inconnu : ?)\n"


def test_match_expression_on_plain_values():
    assert out('''
for n in [1, 3, 9]
    print(match n
        1 => "un"
        3 => "trois"
        _ => "autre"
    end)
end
''') == "un\ntrois\nautre\n"


def test_result_methods():
    assert out('''
r = divide(6.0, 3.0)
print(r.is_ok(), r.is_err(), r.unwrap())
print(divide(1.0, 0.0).unwrap_or(-1.0), divide(1.0, 0.0).message())
''', DIVIDE) == "true false 2.0\n-1.0 division par zéro\n"


def test_unwrap_on_err_stops_the_program_with_the_message():
    _, err, code = run_src(prog("print(divide(1.0, 0.0).unwrap())", DIVIDE))
    assert code == 1 and "division par zéro" in err


def test_ok_value_is_widened_to_the_declared_float():
    assert out("print(one())", "fun one() -> Result[Float]\n    return Ok(1)\nend") == "Ok(1.0)\n"


def test_result_of_string_and_list():
    top = '''fun names() -> Result[List[String]]
    return Ok(["a", "b"])
end
fun hello() -> Result[String]
    return Ok("salut")
end'''
    assert out("print(names(), hello())", top) == 'Ok(["a", "b"]) Ok(salut)\n'


def test_non_exhaustive_result_match_is_an_error():
    msg = compile_error("match divide(1.0, 2.0)\n    Ok(v) => print(v)\nend", DIVIDE)
    assert "ne couvre pas le cas `Err(...)`" in msg


def test_match_used_as_value_needs_a_wildcard():
    assert "doit couvrir tous les cas" in compile_error("x = match 3\n    1 => \"a\"\nend")


def test_question_mark_outside_a_result_function_is_an_error():
    msg = compile_error("x = divide(1.0, 2.0)?", DIVIDE)
    assert "qui retourne un `Result" in msg


def test_question_mark_on_a_non_result_is_an_error():
    top = "fun f() -> Result[Int]\n    x = 3?\n    return Ok(x)\nend"
    assert "s'applique à un `Result`" in compile_error("print(f())", top)


def test_ok_with_wrong_type_is_an_error():
    top = 'fun f() -> Result[Int]\n    return Ok("texte")\nend'
    assert "Int" in compile_error("print(f())", top)


def test_err_needs_a_string():
    top = "fun f() -> Result[Int]\n    return Err(42)\nend"
    assert "String" in compile_error("print(f())", top)


def test_ok_pattern_on_a_non_result_is_an_error():
    assert "ne s'applique qu'à un `Result`" in compile_error("match 3\n    Ok(v) => print(v)\n    _ => print(0)\nend")


# ── try / catch / fail ────────────────────────────────────────────────────────

RISKY = '''fun risky(n: Int) -> Int
    if n == 3
        fail("trois interdit")
    end
    return 10 / n
end'''


def test_try_catch_catches_fail_and_runtime_errors():
    assert out('''
for i in [1, 0, 3, 5]
    try
        print("ok {risky(i)}")
    catch e
        print("erreur : {e.message}")
    end
end
''', RISKY) == "ok 10\nerreur : division par zéro\nerreur : trois interdit\nok 2\n"


def test_variables_changed_inside_try_keep_their_value_after_an_error():
    assert out('''
total = 0
for i in [1, 0, 5]
    try
        total = total + risky(i)
    catch e
        total = total + 1000
    end
end
print(total)
''', RISKY) == "1012\n"


def test_catches_index_and_key_errors_and_gives_the_message():
    assert out('''
xs = [1, 2]
try
    print(xs[7])
catch e: Error
    print(e)
end
m = {"a": 1}
try
    print(m["zzz"])
catch e
    print("clé : {e.message}")
end
''') == ("indice 7 hors limites : la liste contient 2 élément(s)\n"
         "clé : clé \"zzz\" introuvable dans la map (utilisez has() ou get_or())\n")


def test_return_break_continue_inside_try_leave_the_frame_cleanly():
    top = RISKY + '''
fun safe(n: Int) -> Int
    try
        return risky(n)
    catch err
        return -1
    end
end'''
    # des milliers d'appels : un cadre oublié sur la pile ferait planter le programme
    assert out('''
s = 0
for i in 0..3000
    s = s + safe(i % 5)
end
print(s)
n = 0
while true
    try
        n = n + 1
        if n > 4000
            break
        end
        if n % 2 == 0
            continue
        end
    catch e
        print("x")
    end
end
print(n)
''', top) == "%d\n4001\n" % sum({0: -1, 1: 10, 2: 5, 3: -1, 4: 2}[i % 5] for i in range(3000))


def test_error_after_a_try_block_is_not_caught_by_it():
    _, err, code = run_src(prog('''
try
    print("dans try")
catch e
    print("jamais")
end
fail("hors du try")
'''))
    assert code == 1 and "hors du try" in err


def test_uncaught_fail_stops_with_the_message():
    _, err, code = run_src(prog('fail("boum")'))
    assert code == 1 and "boum" in err


def test_nested_try_inner_catch_runs_first():
    assert out('''
try
    try
        fail("interne")
    catch a
        print("a : {a.message}")
        fail("rejeté")
    end
catch b
    print("b : {b.message}")
end
''') == "a : interne\nb : rejeté\n"


def test_question_mark_inside_try_pops_the_frame():
    top = DIVIDE + '''
fun f(b: Float) -> Result[Float]
    try
        x = divide(1.0, b)?
        return Ok(x)
    catch e
        return Err("attrapé")
    end
end'''
    assert out("for i in 0..2000\n    f(0.0)\nend\nprint(f(0.0), f(2.0))", top) == "Err(division par zéro) Ok(0.5)\n"


def test_catch_type_must_be_error():
    assert "catch" in compile_error("try\n    print(1)\ncatch e: Int\n    print(2)\nend")


def test_error_has_only_a_message_field():
    assert "message" in compile_error("try\n    print(1)\ncatch e\n    print(e.code)\nend")


def test_function_ending_in_try_catch_that_both_return_is_complete():
    top = '''fun f() -> Int
    try
        return 1
    catch e
        return 2
    end
end'''
    assert out("print(f())", top) == "1\n"


# ── Optionnels sur types valeur + promotion après test null ──────────────────

def test_optional_float_narrowing_and_to_float():
    o = out('''
for s in ["4", "oops"]
    v = s.to_float()
    if v == null
        print("non : {s}")
        continue
    end
    print(v + 1.0)
end
x: Int? = null
print(x, x == null)
x = 5
print(x, x != null)
''')
    assert o.splitlines() == ["5.0", "non : oops", "null true", "5 true"]


def test_optional_return_and_early_exit():
    top = '''fun half(s: String) -> Float?
    n = s.to_float()
    if n == null
        return null
    end
    return n / 2.0
end'''
    assert out('print(half("5"), half("z"))', top).strip() == "2.5 null"


def test_optional_unchecked_use_is_error():
    e = compile_error('v = "3".to_float()\nprint(v + 1.0)')
    assert "peut être null" in e


def test_string_methods_and_ordering():
    o = out('print("abc" < "abd", "b" >= "a", "hello".slice(1, 3), "42".to_int())')
    assert o.strip() == "true true el 42"


def test_string_iteration_unicode():
    assert out('for ch in "aé€"\n    print(ch)\nend').split() == ["a", "é", "€"]


# ── Modules de la stdlib et @native ──────────────────────────────────────────

def test_import_math_and_io():
    o = out('''print(math.floor(3.7), math.gcd(12, 18), math.is_prime(13), math.PI > 3.14)
try
    io.read("/nonexistent/zzz")
catch e
    print("capturé")
end''', top="import math\nimport io")
    assert o.splitlines() == ["3.0 6 true true", "capturé"]


def test_unknown_module_and_member_errors():
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c("import nope\n", "t.air")
    assert "introuvable" in str(ei.value.errors[0])
    with pytest.raises(CompileErrors) as ei:
        driver.compile_to_c(prog("print(math.zzz(1.0))", "import math"), "t.air")
    assert "n'a pas de fonction `zzz`" in str(ei.value.errors[0])


def test_calculator_example():
    exe_src = open(os.path.join(os.path.dirname(__file__), "..", "examples", "calculator.air"), encoding="utf-8").read()
    o, e, code = run_src(exe_src, "10 + 5\n7 / 0\nsqrt 16\nquit\n")
    assert code == 0, e
    assert "= 15" in o and "Division par zéro" in o and "√16 = 4" in o


def test_trait_blueprint_runs():
    top = '''trait Speaker
    fun speak() -> String
end
blueprint Dog implements Speaker
    fun speak() -> String
        return "Wouf"
    end
end'''
    assert out("print(Dog.new().speak())", top).strip() == "Wouf"
