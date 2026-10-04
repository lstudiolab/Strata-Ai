#include "strata11/Learner.hpp"
#include "strata11/Instructions.hpp"
#include <iostream>
#include <string>
#include <vector>

using namespace strata11;

static std::string arg(int argc,char**argv,const std::string& name,const std::string& fallback=""){
    for(int i=1;i+1<argc;++i) if(std::string(argv[i])==name) return argv[i+1];
    return fallback;
}

static std::string decode64(const std::string& input){
    static const std::string alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::vector<int> table(256,-1);
    for(int i=0;i<64;++i) table[static_cast<unsigned char>(alphabet[i])]=i;
    std::string out;
    int val=0,bits=-8;
    for(unsigned char c:input){
        if(table[c]<0) break;
        val=(val<<6)+table[c];
        bits+=6;
        if(bits>=0){
            out.push_back(static_cast<char>((val>>bits)&0xFF));
            bits-=8;
        }
    }
    return out;
}

int main(int argc,char**argv){
    Learner learner(arg(argc,argv,"--db","strata11/data/learning.tsv"));
    const std::string mode=arg(argc,argv,"--mode","context");
    if(mode=="instructions"){
        std::cout<<Instructions::system_context(arg(argc,argv,"--question"))<<std::flush;
        return 0;
    }
    if(mode=="learn"){
        std::string assistant,question,answer;
        std::getline(std::cin,assistant);
        std::getline(std::cin,question);
        std::getline(std::cin,answer);
        assistant=decode64(assistant);
        question=decode64(question);
        answer=decode64(answer);
        if(question.empty()||answer.empty()) return 2;
        LearningRecord r;
        r.id=arg(argc,argv,"--id");
        r.assistant=assistant.empty()?"strata":assistant;
        r.question=question;
        r.answer=answer;
        std::cout<<learner.learn(r)<<'\n';
        return 0;
    }
    if(mode=="context"){
        std::string question((std::istreambuf_iterator<char>(std::cin)),std::istreambuf_iterator<char>());
        std::cout<<learner.context_for(question)<<std::flush;
        return 0;
    }
    return 2;
}
