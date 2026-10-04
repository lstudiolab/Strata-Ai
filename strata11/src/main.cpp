#include "strata11/Model.hpp"
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

using namespace strata;

static std::mutex model_mutex;

static std::string arg(int ac, char** av, const std::string& name, const std::string& fallback = "") {
    for (int i = 1; i + 1 < ac; ++i) {
        if (std::string(av[i]) == name) return av[i + 1];
    }
    return fallback;
}

static std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 16);
    for (char c : value) {
        switch (c) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) out += ' ';
                else out += c;
        }
    }
    return out;
}

static std::string json_message(const std::string& body) {
    const auto key = body.find("\"message\"");
    if (key == std::string::npos) return {};

    auto colon = body.find(':', key);
    if (colon == std::string::npos) return {};

    auto quote = body.find('"', colon + 1);
    if (quote == std::string::npos) return {};

    std::string out;
    bool escaped = false;
    for (size_t i = quote + 1; i < body.size(); ++i) {
        const char c = body[i];
        if (escaped) {
            switch (c) {
                case 'n': out += '\n'; break;
                case 'r': out += '\r'; break;
                case 't': out += '\t'; break;
                case '\\': out += '\\'; break;
                case '"': out += '"'; break;
                default: out += c; break;
            }
            escaped = false;
            continue;
        }
        if (c == '\\') {
            escaped = true;
            continue;
        }
        if (c == '"') break;
        out += c;
    }
    return out;
}

static std::string request_path(const std::string& request) {
    const auto first_space = request.find(' ');
    if (first_space == std::string::npos) return {};
    const auto second_space = request.find(' ', first_space + 1);
    if (second_space == std::string::npos) return {};
    return request.substr(first_space + 1, second_space - first_space - 1);
}

static std::string request_method(const std::string& request) {
    const auto first_space = request.find(' ');
    if (first_space == std::string::npos) return {};
    return request.substr(0, first_space);
}

static size_t content_length(const std::string& request) {
    const std::string header = "Content-Length:";
    const auto pos = request.find(header);
    if (pos == std::string::npos) return 0;

    auto start = pos + header.size();
    while (start < request.size() && (request[start] == ' ' || request[start] == '\t')) ++start;

    size_t end = start;
    while (end < request.size() && request[end] >= '0' && request[end] <= '9') ++end;

    try {
        return std::stoull(request.substr(start, end - start));
    } catch (...) {
        return 0;
    }
}

static void send_all(int fd, const std::string& data) {
    size_t sent = 0;
    while (sent < data.size()) {
        const ssize_t n = send(fd, data.data() + sent, data.size() - sent, 0);
        if (n <= 0) return;
        sent += static_cast<size_t>(n);
    }
}

static void reply(
    int fd,
    int code,
    const std::string& status,
    const std::string& content_type,
    const std::string& body
) {
    std::ostringstream headers;
    headers
        << "HTTP/1.1 " << code << ' ' << status << "\r\n"
        << "Content-Type: " << content_type << "\r\n"
        << "Content-Length: " << body.size() << "\r\n"
        << "Access-Control-Allow-Origin: *\r\n"
        << "Access-Control-Allow-Headers: Content-Type\r\n"
        << "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
        << "Connection: close\r\n\r\n";

    send_all(fd, headers.str());
    send_all(fd, body);
}

static void sse_reply(int fd, const std::string& body) {
    std::ostringstream headers;
    headers
        << "HTTP/1.1 200 OK\r\n"
        << "Content-Type: text/event-stream; charset=utf-8\r\n"
        << "Cache-Control: no-cache, no-transform\r\n"
        << "Connection: keep-alive\r\n"
        << "Access-Control-Allow-Origin: *\r\n"
        << "Access-Control-Allow-Headers: Content-Type\r\n"
        << "X-Accel-Buffering: no\r\n"
        << "Content-Length: " << body.size() << "\r\n\r\n";

    send_all(fd, headers.str());
    send_all(fd, body);
}

static bool ends_with(const std::string& value, const std::string& suffix) {
    return value.size() >= suffix.size() &&
           value.compare(value.size() - suffix.size(), suffix.size(), suffix) == 0;
}

static std::string mime_type(const std::string& path) {
    if (ends_with(path, ".html")) return "text/html; charset=utf-8";
    if (ends_with(path, ".js")) return "application/javascript; charset=utf-8";
    if (ends_with(path, ".css")) return "text/css; charset=utf-8";
    if (ends_with(path, ".json")) return "application/json; charset=utf-8";
    if (ends_with(path, ".svg")) return "image/svg+xml";
    if (ends_with(path, ".png")) return "image/png";
    if (ends_with(path, ".jpg") || ends_with(path, ".jpeg")) return "image/jpeg";
    if (ends_with(path, ".webp")) return "image/webp";
    return "application/octet-stream";
}

static bool serve_static(int fd, const std::string& path) {
    std::string relative;
    if (path == "/" || path == "/index.html") {
        relative = "app/static/index.html";
    } else if (path.rfind("/static/", 0) == 0) {
        relative = "app/static/" + path.substr(8);
    } else {
        return false;
    }

    if (relative.find("..") != std::string::npos) {
        reply(fd, 403, "Forbidden", "application/json", "{\"error\":\"Forbidden\"}");
        return true;
    }

    std::ifstream file(relative, std::ios::binary);
    if (!file) {
        reply(fd, 404, "Not Found", "application/json", "{\"error\":\"Static file not found\"}");
        return true;
    }

    std::string data((std::istreambuf_iterator<char>(file)), {});
    reply(fd, 200, "OK", mime_type(relative), data);
    return true;
}

static std::string train_on_experience(
    Model& model,
    const std::string& prompt,
    const std::string& answer,
    const std::string& checkpoint
) {
    const std::string experience = "User: " + prompt + "\nStrata: " + answer + "\n";
    std::vector<unsigned char> training(experience.begin(), experience.end());

    const float loss = model.train(training, 0.0003f);
    model.save(checkpoint);

    std::ostringstream out;
    out << "loss=" << loss << " learned=" << training.size();
    return out.str();
}

static std::string fallback_answer(const std::string& prompt) {
    if (prompt.empty()) return "I received an empty prompt.";
    const std::string lower = [&] {
        std::string v = prompt;
        std::transform(v.begin(), v.end(), v.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        return v;
    }();

    if (lower == "hi" || lower == "hello" || lower == "hey" || lower == "yo") {
        return "Hello. I am Strata. I received your message and I am learning from this conversation.";
    }

    if (prompt.back() == '?') {
        return "I received your question: " + prompt +
               "\n\nMy native C++ model is still learning, but I will respond instead of leaving the message blank.";
    }

    return "I received: " + prompt +
           "\n\nStrata is online. I am using the native C++ learning system for this conversation.";
}

static void client(int fd, Model& model, const std::string& checkpoint) {
    std::string request;
    char buffer[16384];

    while (request.find("\r\n\r\n") == std::string::npos && request.size() < 131072) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n <= 0) {
            close(fd);
            return;
        }
        request.append(buffer, static_cast<size_t>(n));
    }

    const auto header_end = request.find("\r\n\r\n");
    if (header_end == std::string::npos) {
        reply(fd, 400, "Bad Request", "application/json", "{\"error\":\"Malformed HTTP request\"}");
        close(fd);
        return;
    }

    const auto method = request_method(request);
    const auto path = request_path(request);
    const size_t wanted_body = content_length(request);
    std::string body = request.substr(header_end + 4);

    while (body.size() < wanted_body && request.size() < 16 * 1024 * 1024) {
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n <= 0) break;
        body.append(buffer, static_cast<size_t>(n));
    }

    if (body.size() > wanted_body && wanted_body > 0) {
        body.resize(wanted_body);
    }

    if (method == "OPTIONS") {
        reply(fd, 204, "No Content", "text/plain", "");
        close(fd);
        return;
    }

    if (method == "GET" && path == "/health") {
        reply(fd, 200, "OK", "application/json",
              "{\"status\":\"ok\",\"engine\":\"strata-cpp\",\"interface\":\"strata-ui-v1\",\"learning\":\"online\"}");
        close(fd);
        return;
    }

    if (method == "GET" && path == "/api/models") {
        reply(fd, 200, "OK", "application/json",
              "{\"models\":[{\"id\":\"strata\",\"name\":\"Strata\",\"version\":\"1.0\",\"learning\":true,\"engine\":\"cpp\"}]}");
        close(fd);
        return;
    }

    if (method == "POST" && path == "/api/chat") {
        const std::string prompt = json_message(body);
        if (prompt.empty()) {
            reply(fd, 400, "Bad Request", "application/json", "{\"error\":\"Message is required.\"}");
            close(fd);
            return;
        }

        std::string answer;
        {
            std::lock_guard<std::mutex> lock(model_mutex);
            answer = model.generate(prompt, 180, 0.85f);
            if (answer.size() < 2) answer = fallback_answer(prompt);
        }

        std::thread([prompt, answer, &model, checkpoint] {
            std::lock_guard<std::mutex> lock(model_mutex);
            const auto info = train_on_experience(model, prompt, answer, checkpoint);
            std::cout << "online learning: " << info << std::endl;
        }).detach();

        // The native server speaks the same event contract as the existing UI.
        // It sends status -> delta -> answer -> done, so no adapter is needed.
        std::ostringstream events;
        events << "data: {\"type\":\"status\",\"message\":\"Thinking...\"}\n\n";
        events << "data: {\"type\":\"delta\",\"message\":\"" << json_escape(answer) << "\"}\n\n";
        events << "data: {\"type\":\"answer\",\"message\":\"" << json_escape(answer) << "\",\"model\":\"strata\",\"engine\":\"cpp\",\"learning\":true}\n\n";
        events << "data: {\"type\":\"done\"}\n\n";

        sse_reply(fd, events.str());
        close(fd);
        return;
    }

    if (method == "GET" && serve_static(fd, path)) {
        close(fd);
        return;
    }

    reply(fd, 404, "Not Found", "application/json", "{\"error\":\"Not found\"}");
    close(fd);
}

static int train_dataset(
    const std::string& dataset,
    const std::string& checkpoint,
    int epochs,
    float learning_rate
) {
    std::ifstream file(dataset);
    if (!file) {
        std::cerr << "dataset not found: " << dataset << "\n";
        return 1;
    }

    Model model;
    std::string line;

    for (int epoch = 1; epoch <= epochs; ++epoch) {
        file.clear();
        file.seekg(0);

        double loss = 0.0;
        size_t count = 0;

        while (std::getline(file, line)) {
            if (line.size() < 2) continue;
            std::vector<unsigned char> training(line.begin(), line.end());
            loss += model.train(training, learning_rate);
            ++count;
        }

        std::cout << "epoch " << epoch
                  << " loss " << (count ? loss / count : 0.0)
                  << std::endl;

        model.save(checkpoint);
    }

    return 0;
}

int main(int argc, char** argv) {
    if (arg(argc, argv, "--mode") == "train") {
        return train_dataset(
            arg(argc, argv, "--dataset", "data/train.txt"),
            arg(argc, argv, "--checkpoint", "data/strata.model"),
            std::stoi(arg(argc, argv, "--epochs", "1")),
            std::stof(arg(argc, argv, "--learning-rate", "0.001"))
        );
    }

    Model model;
    const std::string checkpoint = arg(argc, argv, "--model", "data/strata.model");
    model.load(checkpoint);

    const int port = std::stoi(
        arg(argc, argv, "--port", std::getenv("PORT") ? std::getenv("PORT") : "8000")
    );

    const int server = socket(AF_INET, SOCK_STREAM, 0);
    if (server < 0) return 1;

    int reuse = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons(static_cast<uint16_t>(port));

    if (bind(server, reinterpret_cast<sockaddr*>(&address), sizeof(address)) < 0) return 1;
    if (listen(server, 32) < 0) return 1;

    std::cout
        << "Strata C++ online-learning engine: "
        << model.parameters()
        << " parameters, port "
        << port
        << std::endl;

    while (true) {
        const int fd = accept(server, nullptr, nullptr);
        if (fd >= 0) {
            std::thread(client, fd, std::ref(model), checkpoint).detach();
        }
    }
}