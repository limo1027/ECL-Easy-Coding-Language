# ============================================================
# ECL 全特性测试
# 覆盖：变量、类型、函数、单行函数、控制流、异常、ref、
#       swap、类、goto、const、= / ==、>=
# ============================================================

# ---------- 1. 基础变量与类型 ----------
int x <- 42
str name <- "world"
float pi <- 3.14
bool flag <- True

print("hello,", name)
print(x)
print(pi)
print(flag)

# 类型转换：int 接收 float 时截断
int y <- 3.7
print("y =", y)          # 3

# 类型转换：float 接收 int
float z <- 7
print("z =", z)          # 7.0

# ---------- 2. 运算符 ----------
print(1 + 2)             # 3
print(10 - 3)            # 7
print(4 * 5)             # 20
print(10 / 3)            # 3.3333333333333335
print(10 // 3)           # 3
print(10 % 3)            # 1
print(2 ** 8)            # 256
print(-5)                # -5
print(~5)                # -6
print(not True)          # False

# 比较：= 和 == 都做相等
if x = 42:
    print("x = 42 (用 =)")
end
if x == 42:
    print("x == 42 (用 ==)")
end

if x >= 42:
    print("x >= 42")
end

# 三目表达式
int bigger <- 10 if x > 0 else 20
print("bigger =", bigger)   # 10

# ---------- 3. 函数 ----------
def add(int a, int b) -> int:
    return a + b
end

def greet(str n) -> str:
    return "Hi, " + n
end

print(add(3, 5))          # 8
print(greet("ECL"))       # Hi, ECL

# 默认参数
def power(int base, int exp = 2) -> int:
    return base ** exp
end
print(power(3))           # 9
print(power(2, 10))       # 1024

# 关键字参数
def rect(int w, int h) -> int:
    return w * h
end
print(rect(w = 3, h = 4)) # 12

# 单行函数 + 递归
fact(int n) -> int <- 1 if n < 1 else n * fact(n - 1)
print(fact(5))            # 120

fib(int n) -> int <- n if n < 2 else fib(n - 1) + fib(n - 2)
print(fib(10))            # 55

# 函数作为值

function f <- add
print(f(10, 20))          # 30

# ---------- 4. 控制流 ----------
int total <- 0
for i in 0..=5:
    total <- total + i
end
print("sum 0..5 =", total)   # 15

# for 计数
int count <- 0
for 3:
    count <- count + 1
end
print("count =", count)      # 3

# for 迭代列表
list nums <- [1, 2, 3, 4, 5]
int sum2 <- 0
for n in nums:
    sum2 <- sum2 + n
end
print("sum list =", sum2)    # 15

# while + break + continue
int i <- 0
int even_sum <- 0
while i < 10:
    i <- i + 1
    if i % 2 = 1:
        continue
    end
    even_sum <- even_sum + i
    if i > 6:
        break
    end
end
print("even_sum =", even_sum) # 2+4+6 = 12

# if / elif / else
int score <- 85
if score >= 90:
    print("A")
elif score >= 80:
    print("B")
else:
    print("C")
end

# ---------- 5. 异常 ----------
try:
    int a <- 10
    int b <- 0
    print(a / b)
except ZeroDivisionError as e:
    print("caught:", e)
finally:
    print("finally done")
end

# 自定义异常
try:
    raise ValueError("自定义错误")
except ValueError as e:
    print("caught custom:", e)
end

# ---------- 6. ref 引用 ----------
int original <- 100
ref alias <- original
alias <- 200
print("original =", original)   # 200
print("alias =", alias)         # 200

# ---------- 7. swap ----------
int p <- 1
int q <- 2
p <-> q
print("p =", p, "q =", q)       # p=2 q=1

# ---------- 8. const ----------
const int MAX <- 999
print("MAX =", MAX)             # 999
# MAX <- 0                      # 取消注释会报静态检查错误

# ---------- 9. 列表与字典 ----------
list fruits <- ["apple", "banana", "cherry"]
print(fruits)
print(len(fruits))              # 3
fruits.append("date")
print(fruits)                   # ['apple', 'banana', 'cherry', 'date']
print(fruits[1])                # banana

dict person <- {"name": "Alice", "age": 30}
print(person["name"])           # Alice
print(person["age"])            # 30

# ---------- 10. goto / label ----------
int n <- 0
label loop_start:
n <- n + 1
print("n =", n)
if n < 3:
    goto loop_start
end

# ---------- 11. 类与对象 ----------
class Point:
    def __init__(self, int x, int y) -> none:
        self.x <- x
        self.y <- y
        print(x, y)
    end

    def dist(self) -> float:
        return (self.x ** 2 + self.y ** 2) ** 0.5
    end

    def __add__(self, other) -> Point:
        return Point(self.x + other.x, self.y + other.y)
    end
    def move(self, int dx, int dy) -> none:
        self.x <- self.x + dx
        self.y <- self.y + dy
    end
    def __str__(self) -> str:
        return "Point(" + str(self.x) + ", " + str(self.y) + ")"
    end
end

Point pt <- Point(3, 4)
print("dist =", pt.dist())      # 5.0

pt.move(1, 2)
print(pt + Point(3, 4))
print("new x =", pt.x)          # 4
print("new y =", pt.y)          # 6
print("new dist =", pt.dist())  # sqrt(52) ≈ 7.211

# ---------- 12. 综合：简易计算器 ----------
def calc(str op, int a, int b) -> any:
    if op = "+":
        return a + b
    elif op = "-":
        return a - b
    elif op = "*":
        return a * b
    elif op = "/":
        return a / b
    else:
        return none
    end
end

print(calc("+", 10, 5))    # 15
print(calc("-", 10, 5))    # 5
print(calc("*", 10, 5))    # 50
print(calc("/", 10, 5))    # 2.0
print(calc("?", 10, 5))    # none

code c <- `print("from code object")`
c.run()                    # from code object

int captured <- 100
code c2 <- `print("captured =", captured)`
c2.run()                   # captured = 100

code c3 <- `
    int result <- 42
    str msg <- "done"
`
global g <- c3.run();
print(g.result)            # 42
print(g.msg)               # done
print(g.keys())            # ["result", "msg"]

print("=== 测试 ref ===")
int d <- 100
print("(修改前) d是:", d)
ref e <- d
e <- 200
print("(修改指针后) d是:", d)
d <- 300
print("(修改原数字后) 指针是:", d)
print("=== 全部测试完成 ===")