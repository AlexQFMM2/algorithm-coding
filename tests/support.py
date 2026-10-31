"""Original, self-contained fixtures; never read the user's private problem bank."""
import json
from pathlib import Path

from tools.array_cases import generated_cases

SORT_SOURCE = r'''
#include <algorithm>
#include <iostream>
#include <vector>
int main() {
    int size; std::cin >> size;
    std::vector<int> data(size);
    for (auto &value : data) std::cin >> value;
    std::sort(data.begin(), data.end());
    for (int value : data) std::cout << value << ' ';
}
'''
KTH_SOURCE = r'''
#include <algorithm>
#include <iostream>
#include <vector>
int main() {
    int size, rank; std::cin >> size >> rank;
    std::vector<int> data(size);
    for (auto &value : data) std::cin >> value;
    std::nth_element(data.begin(), data.begin() + rank - 1, data.end());
    std::cout << data[rank - 1];
}
'''


def copy_problem(root, name):
    """Materialize synthetic test data only inside the supplied temporary root."""
    kind = {"快速排序": "sort", "归并排序": "sort", "第k个数": "kth", "逆序对的数量": "inversions"}[name]
    incoming, outgoing = {
        "sort": ("5\n3 1 2 4 5\n", "1 2 3 4 5\n"),
        "kth": ("5 3\n2 4 1 5 3\n", "3\n"),
        "inversions": ("6\n2 3 4 5 6 1\n", "5\n"),
    }[kind]
    destination = Path(root) / "题库" / name
    tests = destination / "tests"
    tests.mkdir(parents=True)
    (destination / "题目.md").write_text("# 合成测试夹具\n\n仅供应用回归验证，不读取个人题库。", encoding="utf-8")
    (destination / "practice.json").write_text(json.dumps({"title": name, "samples": [{"input": incoming, "output": outgoing}]}), encoding="utf-8")
    if kind != "inversions":
        (destination / "main.cpp").write_text(KTH_SOURCE if kind == "kth" else SORT_SOURCE, encoding="utf-8")
    for index, case in enumerate(generated_cases(kind, 788), 1):
        stem = f"{index:03}-{case['name']}"
        (tests / (stem + ".in")).write_text(case["input"], encoding="utf-8")
        (tests / (stem + ".out")).write_text(case["output"], encoding="utf-8")
    return destination
