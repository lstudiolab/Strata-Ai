#include "strata11/Instructions.hpp"
#include <algorithm>
#include <cctype>
#include <sstream>
#include <unordered_set>

namespace strata11 {

const BasicKnowledge& Instructions::built_in() {
    static const BasicKnowledge knowledge{
        "You are Strata 1.1, a local learning intelligence inside the Strata AI system.",
        "Be useful, direct, natural, accurate, and conversational. Understand the user's intent before responding. Ask for clarification only when necessary.",
        "Treat normal conversation as conversation. Track references such as it, that, this, they, and previous turns. Do not mistake ordinary questions, greetings, opinions, requests, or follow-ups for commands to the operating system.",
        "You already possess general-purpose assistant knowledge: language, arithmetic concepts, programming concepts, writing, reasoning, common science, history, geography, and everyday conversation. Learned examples are experience, not unquestionable truth. Never invent facts just because a learned example exists."
    };
    return knowledge;
}

bool Instructions::is_greeting(const std::string& input) {
    std::string s;
    for (unsigned char c : input) s += static_cast<char>(std::tolower(c));
    while (!s.empty() && std::ispunct(static_cast<unsigned char>(s.back()))) s.pop_back();
    static const std::unordered_set<std::string> greetings={
        "hi","hello","hey","yo","hiya","howdy","good morning","good afternoon","good evening"
    };
    return greetings.count(s)>0;
}

bool Instructions::is_direct_address(const std::string& input) {
    if (input.empty()) return false;
    std::string s;
    for (unsigned char c : input) s += static_cast<char>(std::tolower(c));
    const bool question = s.find('?') != std::string::npos;
    const bool second_person =
        s.find("you ") != std::string::npos ||
        s.rfind("you",0)==0 ||
        s.find("your ") != std::string::npos;
    const bool assistant_terms =
        s.find("ai") != std::string::npos ||
        s.find("assistant") != std::string::npos ||
        s.find("strata") != std::string::npos ||
        s.find("model") != std::string::npos;
    return question || second_person || assistant_terms;
}

std::string Instructions::system_context(const std::string& user_message) {
    const auto& k=built_in();
    std::ostringstream out;
    out<<k.identity<<"\n"<<k.behavior<<"\n"<<k.conversation_rules<<"\n"<<k.knowledge_rules;
    if(is_greeting(user_message))
        out<<"\nThe user is greeting you. Respond naturally and briefly.";
    else if(is_direct_address(user_message))
        out<<"\nThe user is directly communicating with you. Interpret the message semantically and answer the intended request.";
    else
        out<<"\nTreat this as a normal user message and infer its intent from context.";
    return out.str();
}

}
