def fibonacci_numbers(n):
    fib_series = [0, 1]
    
    while len(fib_series) < n:
        fib_series.append(fib_series[-1] + fib_series[-2])
         
    return fib_series[:n]

# ilk 10 terimi ekrana yazdiran kod
print(fibonacci_numbers(10))  # çıktı: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]