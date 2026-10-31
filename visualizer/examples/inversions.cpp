// Original teaching example for algorithm-coding: count inversions by merging.
// Copy into a problem package as visualize.cpp; this file is not a user's attempt.
#include "visualization.hpp"
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using namespace std;
using wbviz::Json;

wbviz::Recorder trace;
vector<int> nums, tmp;
vector<pair<int, int>> calls;
vector<string> recent;
long long cnt = 0;

// Presentation helper: records actual array values without changing the algorithm.
void show(int line, const string &kind, const string &message,
          int l, int mid, int r, int ll = -1, int rl = -1, int k = 0,
          long long before = -1, Json pairs = Json::array()) {
    trace.set("nums", nums);
    trace.set("tmp", tmp);
    if (ll >= l && ll <= mid) trace.select("nums", ll, mid);
    if (rl > mid && rl <= r) trace.patch("nums", rl);
    if (k) trace.select("tmp", 0, k - 1);
    string stack;
    for (const auto &call : calls) {
        if (!stack.empty()) stack += " → ";
        stack += "[" + to_string(call.first) + "," + to_string(call.second) + "]";
    }
    recent.push_back(message);
    if (recent.size() > 3) recent.erase(recent.begin());
    string log;
    for (const auto &text : recent) log += text + "\n";
    trace.set("log", log);
    Json state = {{"l", l}, {"mid", mid}, {"r", r},
                  {"ll", ll < 0 ? Json("—") : Json(ll)},
                  {"rl", rl < 0 ? Json("—") : Json(rl)}, {"k", k},
                  {"递归路径", stack.empty() ? "已完成" : stack}};
    trace.step(line, message, {{"kind", kind}, {"state", state}, {"before", before < 0 ? cnt : before},
                              {"after", cnt}, {"pairs", pairs}});
}

void mergeSort(int l, int r) {
    calls.push_back({l, r});
    if (l >= r) {
        show(__LINE__, "single", "区间只剩一个元素，本身已有序，返回上一层。", l, l, r);
        calls.pop_back();
        return;
    }
    int mid = (l + r) / 2;
    show(__LINE__, "split", "先分别处理左右两段；两段都有序后，才能整段统计跨区间的逆序对。", l, mid, r);
    mergeSort(l, mid);
    mergeSort(mid + 1, r);

    int ll = l, rl = mid + 1, k = 0;
    show(__LINE__, "merge", "左右两段已经有序。k 回到 0，从 tmp 开头覆盖；灰色的旧值暂时不用。", l, mid, r, ll, rl, k);
    while (ll <= mid && rl <= r) {
        show(__LINE__, "compare", "比较左侧 nums[ll] = " + to_string(nums[ll]) + " 与右侧 nums[rl] = " + to_string(nums[rl]) + "。", l, mid, r, ll, rl, k);
        if (nums[ll] > nums[rl]) {
            Json pairs = Json::array();
            for (int p = ll; p <= mid; ++p) pairs.push_back(Json::array({nums[p], nums[rl]}));
            long long before = cnt;
            int count_line = __LINE__ + 1;
            cnt += mid - ll + 1;
            tmp[k++] = nums[rl];
            show(count_line, "count", "左边已经有序：当前 " + to_string(nums[ll]) + " 都比 " + to_string(nums[rl]) +
                 " 大，左边剩下的也都比它大。本步新增 " + to_string(mid - ll + 1) + " 对，不只是 1 对。", l, mid, r, ll, rl, k, before, pairs);
            ++rl;
        } else {
            bool equal = nums[ll] == nums[rl];
            int copy_line = __LINE__ + 1;
            tmp[k++] = nums[ll];
            show(copy_line, equal ? "equal" : "take_left", equal ? "两个值相等，不构成逆序对。先取左边，不增加计数。" :
                 "左边这个数更小，右边剩余的数也不会更小。先取左边，不增加计数。", l, mid, r, ll, rl, k);
            ++ll;
        }
    }
    while (ll <= mid) {
        int copy_line = __LINE__ + 1;
        tmp[k++] = nums[ll];
        show(copy_line, "tail", "右段已取完。跨区间逆序对已经统计，剩余左段直接复制，不再加计数。", l, mid, r, ll, rl, k);
        ++ll;
    }
    while (rl <= r) {
        int copy_line = __LINE__ + 1;
        tmp[k++] = nums[rl];
        show(copy_line, "tail", "左段已取完。剩余右段直接复制，不新增逆序对。", l, mid, r, ll, rl, k);
        ++rl;
    }
    int write_line = __LINE__ + 1;
    for (int i = 0; i < k; ++i) nums[l + i] = tmp[i];
    show(write_line, "write_back", "只把本轮写过的 tmp[0.." + to_string(k - 1) + "] 复制回当前区间。后面的旧值不读取，所以不用清零。", l, mid, r, -1, -1, k);
    calls.pop_back();
}

int main() {
    long long n, value;
    if (!(cin >> n) || n < 1 || n > 20) {
        cerr << "第一行 n 必须是 1～20 的整数；演示使用小数组，不会自动截断输入。";
        return 2;
    }
    for (int i = 0; i < n; ++i) {
        if (!(cin >> value) || value < 1 || value > 1000000000) {
            cerr << "请提供恰好 n 个整数，每个值在 1～1000000000 范围内。";
            return 2;
        }
        nums.push_back(static_cast<int>(value));
    }
    string extra;
    if (cin >> extra) { cerr << "输入包含多余内容，元素个数必须与 n 一致。"; return 2; }
    tmp.resize(n);
    trace.array("nums", "nums · 当前数组（下标从 0 开始）", nums);
    trace.array("tmp", "tmp · 本轮已写区域有下划线，其余为未使用或残留值", tmp);
    trace.log("log", "最近步骤");
    trace.layout({"nums", "tmp", "log"});
    show(__LINE__, "start", "准备开始：先把左右两段分别处理成有序，再合并并统计跨区间的逆序对。", 0, -1, n - 1);
    mergeSort(0, static_cast<int>(n) - 1);
    show(__LINE__, "complete", "合并完成。所有逆序对都已统计，答案是 " + to_string(cnt) + "。", 0, -1, n - 1);
    cout << cnt << '\n';
    trace.finish();
}
