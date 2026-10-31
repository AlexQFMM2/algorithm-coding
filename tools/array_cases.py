"""Offline input factories and independent oracles for the initial four problems."""
import random


def count_inversions(values):
    """Independent O(n log n) oracle: compressed ranks and a Fenwick tree."""
    ranks = {value: index for index, value in enumerate(sorted(set(values)), 1)}
    tree = [0] * (len(ranks) + 1)
    total = 0
    for value in reversed(values):
        rank = ranks[value]
        index = rank - 1  # Equal values do not form inversions.
        while index:
            total += tree[index]
            index -= index & -index
        index = rank
        while index < len(tree):
            tree[index] += 1
            index += index & -index
    return total


def generated_cases(kind, seed):
    if kind not in ("sort", "kth", "inversions"):
        raise ValueError(f"Unsupported offline array generator: {kind}")
    rng = random.Random(seed)
    arrays = [("单个元素", [42]), ("两个逆序元素", [2, 1]),
              ("全部相同", [7] * 20), ("重复值", [2, 1, 2, 1, 3]),
              ("已排序", list(range(1, 101))), ("逆序", list(range(100, 0, -1))),
              ("数值边界", [10**9, 1, 10**9, 2, 1])]
    arrays += [(f"随机 {i + 1:02}", [rng.randint(1, 30 if i % 2 else 10**9)
                                   for _ in range(rng.randint(2, 500))]) for i in range(20)]
    arrays += [("十万元素", [rng.randint(1, 10**9) for _ in range(100_000)]),
               ("十万相同元素", [1] * 100_000)]
    if kind == "inversions":
        arrays += [("两个相等元素", [2, 2]), ("相等值跨左右区间", [2, 1, 2, 1]),
                   ("十万元素完全逆序", list(range(100_000, 0, -1)))]
    cases = []
    for label, values in arrays:
        if kind == "inversions":
            cases.append({"name": label, "input": f"{len(values)}\n" + " ".join(map(str, values)) + "\n",
                          "output": f"{count_inversions(values)}\n"})
            continue
        ordered = sorted(values)
        if kind == "sort":
            cases.append({"name": label, "input": f"{len(values)}\n" + " ".join(map(str, values)) + "\n",
                          "output": " ".join(map(str, ordered)) + "\n"})
        else:
            for k in sorted({1, len(values), rng.randint(1, len(values))}):
                cases.append({"name": f"{label} · k={k}",
                              "input": f"{len(values)} {k}\n" + " ".join(map(str, values)) + "\n",
                              "output": f"{ordered[k - 1]}\n"})
    return cases


