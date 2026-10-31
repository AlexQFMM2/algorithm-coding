# 参考算法可视化

本模块复用 Algorithm Visualizer 的 MIT 数组、日志、布局和步骤回放核心，为本地题目包提供参考算法演示。版本、原许可证及适配说明见 [UPSTREAM.md](UPSTREAM.md)。C++ 记录接口是独立实现，只写本地文件；JSON 序列化使用带 MIT 许可的 nlohmann/json 3.12.0。

## 开发与构建

日常启动只需根目录的 `./start.sh`，不需要 Node。修改播放器源码时使用 Node.js 20+：

```bash
npm ci --prefix visualizer
npm run build --prefix visualizer
```

提交源码、`package-lock.json` 和 `workbench/static/vendor/algorithm-visualizer/` 的构建产物（含许可证）。构建没有远端资源导入，前端没有上传、在线编译或 CDN 依赖。`upstream/` 保留实际复用的追踪模型和渲染器，`src/player.js` 从上游 Player / VisualizationViewer 的命令分步及重放逻辑适配而来；应用弹窗由 `src/dialog.jsx` 管理。

## 题目配置

将 [examples/inversions.cpp](examples/inversions.cpp) 复制为本地题目包中的 `visualize.cpp`，在已有 `practice.json` 中加入：

```json
"visualization": {
  "source": "visualize.cpp",
  "title": "逆序对：一次数清左边剩余的配对",
  "input_hint": "第一行 n（1～20），后面恰好 n 个整数（1～1000000000）。"
}
```

配置片段需与已有字段用逗号分隔；不替换样例或测试信息。源文件必须是本题目录内、UTF-8 的普通 `.cpp` 文件名，不接受子目录、绝对路径或符号链接。演示源码应是独立翻译单元，可使用标准库及应用提供的 `visualization.hpp`。不通过编译参数读取其他题目资料。

保存练习草稿后点击列表刷新，即可出现「算法演示」。题目接口返回 `visualization.configured/available/error/title/input_hint/source_path/source_revision`，无声明的题目不显示入口，声明无效时显示原因。首次安装新后端需重启一次。

## 记录接口与协议

`workbench/include/visualization.hpp` 的 `wbviz::Recorder` 提供：

| 调用 | 用途 |
| --- | --- |
| `array(id, title, values)` | 创建一维数组并赋值 |
| `log(id, title)` | 创建文字日志 |
| `layout({id, ...})` | 创建纵向布局，并设为根 |
| `set(id, values_or_text)` | 重设数组或文字；数组高亮也会清除 |
| `select(id, first, last)` | 高亮闭区间 |
| `patch(id, index)` | 突出单个元素 |
| `step(line, message, meta)` | 结束当前步骤，关联源码行和解释 |
| `finish()` | 写出完整 `visualization.json`，失败抛出异常 |

例如：

```cpp
#include "visualization.hpp"
int main() {
    wbviz::Recorder trace;
    trace.array("nums", "数组", {2, 1});
    trace.layout({"nums"});
    trace.step(__LINE__, "观察两个元素。");
    trace.select("nums", 0, 1);
    trace.step(__LINE__, "左边大于右边，构成一对逆序对。",
               {{"kind", "count"}, {"before", 0}, {"after", 1}});
    trace.finish();
}
```

低层 `command(key, method, args)` 使用上游命令格式；参数必须用 `Json::array(...)` 显式构造数组。封装格式是 `{"version":1,"complete":true,"commands":[...]}`。`delay` 命令的参数为 `[源码行号, 元数据]`，标志一步结束。元数据包括 `message`、`kind`、`state`、`before/after`、`pairs`；前端使用 `kind: "count"` 定位下一次计数。`state` 是变量名与可读值的对象，`pairs` 是本步新增的值对数组。

后端仅接受数组（Array1D/Array2D）、日志、纵/横布局和有限的赋值、高亮操作；不执行 JSON 中的脚本。布局只能引用已创建的对象。源码行、数组位置、对象数、数组尺寸、文本长度和步骤完整性都会验证，完整规则在 `workbench/visualization_protocol.py`。后退和跳转复用上游的从头重放方式，使状态与顺序播放一致。

## 执行与记录 API

| 方法与路径 | 用途 |
| --- | --- |
| `POST /api/visualizations` | 生成演示，JSON 字段：`problem`、`input_mode`（sample/manual）、`sample`（从 0 开始）、`input` |
| `GET /api/visualizations?problem=<id>` | 最近 100 条记录摘要 |
| `GET /api/visualization?problem=<id>&run=<id>` | 源码/输入快照；成功时还包含已校验的完整步骤 |

POST 复用应用的本机来源检查和 `X-Workbench-Token`，与判题共享编译运行互斥锁。题目 ID 和查询参数按 URL 编码。状态为 `READY`、`RUNNING`、`INPUT_ERROR`、`CE`、`RE`、`TLE`、`OLE`、`ERROR`；只有 READY 可以播放。演示程序返回 2 表示输入错误，其他非零码表示运行错误。

输入限 16,000 字节、源码限 256,000 字节；编译限 20 秒，执行限 3 秒和 512 MiB。标准输出、错误输出及步骤文件限 4 MiB；最多 4000 步、40000 条命令、32 个对象、每个数组 512 个单元格。演示只是本地运行工具，与现有判题一样具有当前用户的文件权限。

每次生成写到本题 `visualizations/<UTC 时间-随机编号>/`，保存 `source.cpp`、`input.txt`、编译和执行的 stdout/stderr、`result.json` 以及 `visualization.json`。失败时保存可取得的 `visualization.partial.json` 供排查，不显示成功动画。结果包含源代码/步骤哈希、记录接口版本哈希、编译命令、状态和耗时。旧演示读取快照，不执行当前源码；源码或步骤快照损坏时明确拒绝播放。

演示不会调用新建练习或普通判题接口，不增加统计。历史列表上限只影响展示，不自动删文件。运行生成可以在关闭弹窗后完成，重新打开后从历史选择；关闭会取消播放器计时器和界面更新。

## 验证

```bash
python3 -m unittest discover -s tests -v
npm test --prefix visualizer
```

Python 使用临时题目包，测试动态发现、日志、统计隔离、异常、输入和路径限制；逆序对用固定种子 788 的 35 组随机小数组及 8 组边界，与暴力计数及每步配对独立核对。JavaScript 测试实际上游模型的前进、后退和跳转。

浏览器验收使用 Playwright 和 Chromium，全部生成临时数据。开发机首次可执行 `npx --prefix visualizer playwright install chromium` 安装浏览器，或指定本机浏览器：

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome npm run test:browser --prefix visualizer
```

未指定可执行文件时使用 Playwright 安装的 Chromium。可用 `VIZ_SCREENSHOTS=/tmp/visualizer-screenshots` 保留截图。验收覆盖真实 C++ 运行、三对计数、键盘/回退/跳转、草稿与滚动恢复、历史快照、明暗主题、375px 窄屏、低高度横屏、错误输入、旧后端提示及无外网请求。验收不会使用真实题库。
