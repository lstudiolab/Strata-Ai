#pragma once
#include <cstddef>
#include <string>
#include <vector>

namespace strata11 {
struct LearningRecord {
    std::string id;
    std::string assistant;
    std::string question;
    std::string answer;
    double quality = 0.0;
    std::size_t uses = 1;
};

class Learner {
public:
    explicit Learner(std::string database_path);
    std::string learn(const LearningRecord& record);
    std::string context_for(const std::string& question, std::size_t limit = 5) const;
private:
    std::string database_path_;
    std::vector<LearningRecord> load() const;
    static std::string encode(const std::string&);
    static std::string decode(const std::string&);
    static std::vector<std::string> tokens(const std::string&);
    static double similarity(const std::string&, const std::string&);
    static double quality_score(const LearningRecord&);
};
}
