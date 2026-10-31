#pragma once
// Original algorithm-coding adapter. Emits Algorithm Visualizer-compatible
// commands locally; does not contain code from the unlicensed tracers.cpp repo.
#include <nlohmann/json.hpp>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace wbviz {
using Json = nlohmann::json;
class Recorder {
    Json commands_ = Json::array();
    int steps_ = 0;
public:
    void command(const Json &key, const std::string &method, Json args) {
        if (!args.is_array()) throw std::runtime_error("命令参数必须是数组。");
        if (commands_.size() >= 40000) throw std::runtime_error("演示命令超过 40000 条，请缩小输入。");
        commands_.push_back({{"key", key}, {"method", method}, {"args", std::move(args)}});
    }
    void array(const std::string &id, const std::string &title, const Json &values) {
        command(id, "Array1DTracer", Json::array({title})); set(id, values);
    }
    void log(const std::string &id, const std::string &title) { command(id, "LogTracer", Json::array({title})); }
    void layout(const std::vector<std::string> &children) {
        command("layout", "VerticalLayout", Json::array({children}));
        command(nullptr, "setRoot", Json::array({"layout"}));
    }
    void set(const std::string &id, const Json &value) { command(id, "set", Json::array({value})); }
    void select(const std::string &id, int first, int last) {
        if (first <= last) command(id, "select", Json::array({first, last}));
    }
    void patch(const std::string &id, int index) { command(id, "patch", Json::array({index})); }
    void step(int line, const std::string &message, Json meta = Json::object()) {
        if (++steps_ > 4000) throw std::runtime_error("演示超过 4000 步，请缩小输入。");
        meta["message"] = message;
        command(nullptr, "delay", Json::array({line, std::move(meta)}));
    }
    void finish() const {
        if (!steps_) throw std::runtime_error("演示没有步骤。");
        std::string content = Json({{"version", 1}, {"complete", true}, {"commands", commands_}}).dump();
        if (content.size() > 4 * 1024 * 1024) throw std::runtime_error("步骤记录超过 4 MiB，请缩小输入。");
        std::ofstream output("visualization.json", std::ios::binary);
        if (!output || !(output << content)) throw std::runtime_error("无法保存步骤记录。");
        output.close();
        if (!output) throw std::runtime_error("保存步骤记录失败。");
    }
};
}
