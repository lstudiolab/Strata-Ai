#include "strata11/Learner.hpp"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <unordered_set>

namespace strata11 {
static const char* alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

std::string Learner::encode(const std::string& input) {
    std::string out;
    int val = 0, bits = -6;
    for (unsigned char c : input) {
        val = (val << 8) + c;
        bits += 8;
        while (bits >= 0) {
            out.push_back(alphabet[(val >> bits) & 0x3F]);
            bits -= 6;
        }
    }
    if (bits > -6) out.push_back(alphabet[((val << 8) >> (bits + 8)) & 0x3F]);
    while (out.size() % 4) out.push_back('=');
    return out;
}

std::string Learner::decode(const std::string& input) {
    std::vector<int> table(256, -1);
    for (int i = 0; i < 64; ++i) table[static_cast<unsigned char>(alphabet[i])] = i;
    std::string out;
    int val = 0, bits = -8;
    for (unsigned char c : input) {
        if (table[c] < 0) break;
        val = (val << 6) + table[c];
        bits += 6;
        if (bits >= 0) {
            out.push_back(static_cast<char>((val >> bits) & 0xFF));
            bits -= 8;
        }
    }
    return out;
}

Learner::Learner(std::string database_path) : database_path_(std::move(database_path)) {}

std::vector<LearningRecord> Learner::load() const {
    std::ifstream in(database_path_);
    std::vector<LearningRecord> records;
    std::string line;
    while (std::getline(in, line)) {
        std::istringstream row(line);
        std::string a,b,q,ans,quality,uses;
        if (!std::getline(row,a,'\t') || !std::getline(row,b,'\t') ||
            !std::getline(row,q,'\t') || !std::getline(row,ans,'\t') ||
            !std::getline(row,quality,'\t') || !std::getline(row,uses)) continue;
        try {
            LearningRecord r;
            r.id=decode(a); r.assistant=decode(b); r.question=decode(q); r.answer=decode(ans);
            r.quality=std::stod(quality); r.uses=std::max<std::size_t>(1,std::stoull(uses));
            if (!r.question.empty() && !r.answer.empty()) records.push_back(std::move(r));
        } catch (...) {}
    }
    return records;
}

std::vector<std::string> Learner::tokens(const std::string& text) {
    std::string normalized;
    for (unsigned char c : text) normalized += std::isalnum(c) ? static_cast<char>(std::tolower(c)) : ' ';
    std::istringstream in(normalized);
    std::string token;
    std::vector<std::string> result;
    static const std::unordered_set<std::string> stop={
        "the","a","an","and","or","to","of","in","on","for","is","it","this","that",
        "can","you","me","my","i","we","what","how","why","please","with","from","be","are"
    };
    while(in>>token) if(token.size()>1 && !stop.count(token)) result.push_back(token);
    std::sort(result.begin(),result.end());
    result.erase(std::unique(result.begin(),result.end()),result.end());
    return result;
}

double Learner::similarity(const std::string& a,const std::string& b) {
    const auto aa=tokens(a), bb=tokens(b);
    if(aa.empty()||bb.empty()) return 0.0;
    std::unordered_set<std::string> left(aa.begin(),aa.end()), right(bb.begin(),bb.end());
    std::size_t common=0;
    for(const auto& t:left) if(right.count(t)) ++common;
    const std::size_t uni=left.size()+right.size()-common;
    return uni ? static_cast<double>(common)/uni : 0.0;
}

double Learner::quality_score(const LearningRecord& r) {
    double score=0.55;
    if(r.answer.size()>=80) score+=0.10;
    if(r.answer.size()>=300) score+=0.08;
    if(r.answer.size()>12000) score-=0.12;
    if(r.answer.find("I couldn't")!=std::string::npos || r.answer.find("could not complete")!=std::string::npos) score-=0.25;
    if(r.answer.find("ERROR")!=std::string::npos) score-=0.20;
    return std::max(0.05,std::min(1.0,score));
}

std::string Learner::learn(const LearningRecord& input) {
    std::ofstream out(database_path_,std::ios::app);
    if(!out) return {};
    LearningRecord r=input;
    r.quality=quality_score(r);
    if(r.id.empty()) r.id="learn_"+std::to_string(std::hash<std::string>{}(r.question+r.answer));
    out<<encode(r.id)<<'\t'<<encode(r.assistant)<<'\t'<<encode(r.question)<<'\t'
       <<encode(r.answer)<<'\t'<<std::fixed<<std::setprecision(4)<<r.quality<<'\t'<<r.uses<<'\n';
    return r.id;
}

std::string Learner::context_for(const std::string& question,std::size_t limit) const {
    auto records=load();
    struct Ranked{double score;LearningRecord record;};
    std::vector<Ranked> ranked;
    for(const auto& r:records){
        double sim=similarity(question,r.question);
        if(sim<=0) continue;
        double score=sim*0.70+r.quality*0.20+std::log1p(static_cast<double>(r.uses))*0.10;
        ranked.push_back({score,r});
    }
    std::sort(ranked.begin(),ranked.end(),[](const Ranked&a,const Ranked&b){return a.score>b.score;});
    std::ostringstream out;
    std::size_t n=0;
    for(const auto& item:ranked){
        if(n++>=limit) break;
        out<<"- Previous request: "<<item.record.question<<"\n"
           <<"  Learned response pattern: "<<item.record.answer.substr(0,2500)<<"\n";
    }
    return out.str();
}
}
