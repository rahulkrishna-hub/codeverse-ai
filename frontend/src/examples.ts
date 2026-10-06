export type Example = { id: string; title: string; topic: string; code: string };
export const EXAMPLES: Example[] = [
  { id: "vars", title: "Variables and arithmetic", topic: "Variables", code: `x = 10\ny = 20\nresult = x + y\nprint(result)\n` },
  { id: "update", title: "Updating a variable", topic: "Variables", code: `count = 1\ncount = count + 1\ncount = count + 1\nprint(count)\n` },
  { id: "strings", title: "Strings", topic: "Strings", code: `name = "Asha"\ngreeting = "Hello, " + name\nshout = greeting.upper()\nprint(shout)\nprint(len(name))\n` },
  { id: "ifelse", title: "If / else", topic: "Conditions", code: `age = 17\nif age >= 18:\n    print("adult")\nelse:\n    print("minor")\nprint("done")\n` },
  { id: "for", title: "For loop", topic: "Loops", code: `total = 0\nfor i in range(1, 5):\n    total = total + i\n    print(i, total)\nprint("sum:", total)\n` },
  { id: "while", title: "While loop", topic: "Loops", code: `n = 3\nwhile n > 0:\n    print(n)\n    n = n - 1\nprint("liftoff")\n` },
  { id: "func", title: "Functions", topic: "Functions", code: `def square(n):\n    return n * n\n\ndef add_squares(a, b):\n    return square(a) + square(b)\n\nanswer = add_squares(3, 4)\nprint(answer)\n` },
  { id: "list", title: "Lists", topic: "Lists", code: `nums = [5, 2, 8]\nnums.append(1)\nnums[0] = 99\nprint(nums)\nprint(len(nums))\n` },
  { id: "dict", title: "Dictionaries", topic: "Dictionaries", code: `marks = {"maths": 90, "science": 85}\nmarks["english"] = 77\nfor subject in marks:\n    print(subject, marks[subject])\n` },
  { id: "nested", title: "Nested loops", topic: "Loops", code: `for i in range(1, 3):\n    for j in range(1, 4):\n        print(i * j)\n` },
  { id: "search", title: "Linear search", topic: "Searching", code: `items = [4, 9, 2, 7]\ntarget = 2\nfound = -1\nfor i in range(len(items)):\n    if items[i] == target:\n        found = i\n        break\nprint("index:", found)\n` },
  { id: "sort", title: "Bubble sort", topic: "Sorting", code: `a = [4, 2, 5, 1]\nfor i in range(len(a)):\n    for j in range(len(a) - i - 1):\n        if a[j] > a[j + 1]:\n            a[j], a[j + 1] = a[j + 1], a[j]\nprint(a)\n` },
  { id: "error", title: "A bug to debug (ZeroDivisionError)", topic: "Debugging", code: `a = 10\nb = 0\nprint("before")\nc = a / b\nprint("never reached")\n` },
];
