#pragma once
#include <string>

namespace strata11 {

struct BasicKnowledge {
    std::string identity;
    std::string behavior;
    std::string conversation_rules;
    std::string knowledge_rules;
};

class Instructions {
public:
    static const BasicKnowledge& built_in();
    static std::string system_context(const std::string& user_message);
    static bool is_direct_address(const std::string& user_message);
    static bool is_greeting(const std::string& user_message);
};

}
