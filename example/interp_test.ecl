# ============================================================
# ECL 字符串插值（$ 插值）完整测试
# 覆盖：$name、${expr}、$$ 转义、$5/$ 原样输出、
#       转义混用、嵌套表达式、函数/列表/字典插值
# ============================================================

print("=== 1. 基础变量插值 ===")
str name <- "world"
int x <- 42
float pi <- 3.14
bool flag <- True

print("hello, $name")              # hello, world
print("x = $x")                    # x = 42
print("pi = $pi")                  # pi = 3.14
print("flag = $flag")              # flag = True
print("$name is $x years old")     # world is 42 years old

print("")
print("=== 2. 表达式插值 $${...} ===")
print("1 + 2 = ${1 + 2}")          # 1 + 2 = 3
print("x * 2 = ${x * 2}")          # x * 2 = 84
print("nested: ${x * 2 + 1}")      # nested: 85
print("compare: ${x > 0}")         # compare: True
print("ternary: ${10 if x > 0 else 20}")  # ternary: 10

print("")
print("=== 3. 多个插值混合 ===")
str first <- "Alice"
str family_name <- "Smith"
print("$first $family_name")              # Alice Smith
print("$first is $x, $family_name is $x") # Alice is 42, Smith is 42
print("$first + $family_name = ${first + \" \" + family_name}")  # Alice + Smith = Alice Smith

print("")
print("=== 4. $$ 转义 ===")
print("price: $$5")                # price: $5
print("cost: $$100")               # cost: $100
print("dollar: $$")                # dollar: $
print("escape: $$name")            # escape: $name
print("escape: $${1 + 2}")         # escape: ${1 + 2}
print("escape: $$$name")           # escape: $world（$$ 转义 + $name 插值）

print("")
print("=== 5. $ 原样输出（非插值场景）===")
print("no interp: $5")             # no interp: $5
print("no interp: $ ")             # no interp: $
print("end: $")                    # end: $
print("a $ b")                     # a $ b
print("price: $ 100")              # price: $ 100
print("$")                         # $

print("")
print("=== 6. 转义和其他转义混用 ===")
print("tab:\t$name")               # tab:	world
print("newline:\\n$name")          # newline:\nworld（\\n 是字面量 \n）
print("quote: \"$name\"")          # quote: "world"
print("backslash: \\$name")        # backslash: \world
print("mixed: \t$$x\t$name")       # mixed: 	$x	world

print("")
print("=== 7. 列表插值 ===")
list nums <- [1, 2, 3]
print("nums = $nums")              # nums = [1, 2, 3]
print("len = ${len(nums)}")        # len = 3
print("first = ${nums[0]}")        # first = 1
print("last = ${nums[2]}")         # last = 3
print("sum = ${nums[0] + nums[1] + nums[2]}")  # sum = 6

print("")
print("=== 8. 字典插值 ===")
dict person <- {"name": "Alice", "age": 30}
print("name: ${person[\"name\"]}")  # name: Alice
print("age: ${person[\"age\"]}")    # age: 30

print("")
print("=== 9. 函数返回值插值 ===")
def add(int a, int b) -> int:
    return a + b
end

def greet(str n) -> str:
    return "Hi, " + n
end

print("3 + 5 = ${add(3, 5)}")       # 3 + 5 = 8
print("greet: ${greet(\"ECL\")}")   # greet: Hi, ECL

print("")
print("=== 10. 单行函数插值 ===")
square(int n) -> int <- n * n
print("square(5) = ${square(5)}")   # square(5) = 25
print("square($x) = ${square(x)}")  # square(42) = 1764

print("")
print("=== 11. 嵌套 $${} ===")
print("nested: ${add(1, add(2, 3))}")  # nested: 6
print("deep: ${add(add(1, 2), add(3, 4))}")  # deep: 10

print("")
print("=== 12. 字符串拼接 vs 插值 ===")
print("concat: " + "hello, " + name)     # concat: hello, world
print("interp: hello, $name")            # interp: hello, world
print("same result")                     # same result

print("")
print("=== 13. 边界情况 ===")
str empty <- ""
print("empty: '$empty'")                 # empty: ''
print("empty interp: ${empty}")          # empty interp: 
print("dollar only: '$'")                # dollar only: '$'
print("dollar end: '$$'")                # dollar end: '$'
print("double dollar: '$$$$'")           # double dollar: '$$'

print("")
print("=== 14. 循环中的插值 ===")
for i in 0..=2:
    print("iter $i: value = ${i * i}")
end

print("")
print("=== 15. 条件中的插值 ===")
if x > 0:
    print("positive: $x")
else:
    print("non-positive: $x")
end

print("")
print("=== 全部插值测试完成 ===")