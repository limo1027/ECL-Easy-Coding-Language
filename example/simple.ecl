# ==========================================
# ECL AOT 终极综合测试
# ==========================================

print("=== 1 ===")
int a <- 100
int b <- 7
print("100 + 7 =", a + b)
print("100 - 7 =", a - b)
print("100 * 7 =", a * b)
print("100 / 7 =", a / b)
print("100 // 7 =", a // b)
print("100 % 7 =", a % b)
print("2 ** 10 =", 2 ** 10)
str s1 <- "Hello"
str s2 <- "ECL"
print("Concat:", s1 + " " + s2)

print("=== 2 ===")
int total <- 0
int i <- 1
while i <= 100:
    total <- total + i
    i <- i + 1
end
print("Sum 1..100 =", total)

if total > 5000 and total < 10000:
    print("Total is between 5000 and 10000")
elif total == 5050:
    print("Total is exactly 5050")
else:
    print("Total is something else")
end

print("=== 3 ===")
list[int] nums <- [10, 20, 30, 40, 50]
print("List:", nums)
print("Length:", len(nums))
nums[1] <- 25
print("After modify:", nums)

dict scores <- {"Alice": 95, "Bob": 88}
scores["Charlie"] <- 92
print("Dict:", scores)
print("Alice's score:", scores["Alice"])

print("=== 4 ===")
int sum_list <- 0
for n in nums:
    sum_list <- sum_list + n
end
print("Sum of list:", sum_list)

print("=== 5 ===")
def fib(int n) -> int:
    if n <= 1:
        return n
    end
    return fib(n - 1) + fib(n - 2)
end
print("fib(15) =", fib(15))

def greet(str name, str prefix = "Hello") -> str:
    return prefix + ", " + name + "!"
end
print(greet("World"))
print(greet("ECL", "Welcome"))

print("=== 6 ===")
class Point:
    def __init__(int x, int y) -> none:
        self.x <- x
        self.y <- y
    end
    
    def __str__() -> str:
        return "Point(" + str(self.x) + ", " + str(self.y) + ")"
    end
    
    def __add__(Point other) -> Point:
        return Point(self.x + other.x, self.y + other.y)
    end
    
    def dist_sq() -> int:
        return self.x * self.x + self.y * self.y
    end
end

Point p1 <- Point(3, 4)
Point p2 <- Point(1, 2)
Point p3 <- p1 + p2

print("p1 =", p1)
print("p2 =", p2)
print("p1 + p2 =", p3)
print("p1 dist_sq =", p1.dist_sq())

print("=== 7 ===")
try:
    int zero <- 0
    int crash <- 10 / zero
    print("This will not print")
except ZeroDivisionError:
    print("Caught: Division by zero!")
finally:
    print("Finally block executed.")
end

print("=== 8 ===")
list[int] data <- [1, 2, 3]
print("Before free:", data)
free(data)
print("After free:", data)

if data == null:
    print("Data is now null!")
end
print("=== 9 ===")
import math
print("Square of 5:", math_square(5))
print("Cube of 3:", math_cube(3))

list[int] datas <- [1, 2, 3]
print("Before free:", datas)
free(datas)
print("After free:", datas)

if datas == null:
    print("Data is now null!")
end
print("=== 10 ===")
code c <- `int hidden <- 42
print("Executing from code object, hidden =", hidden)`
c.run()

print("=== ALL TESTS COMPLETED ===")