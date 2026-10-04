#include "strata11/Learner.hpp"
#include <iostream>
#include <string>

using namespace strata11;

static std::string arg(int argc,char**argv,const std::string& name,const std::string& fallback=""){
    for(int i=1;i+1<argc;++i) if(std::string(argv[i])==name) return argv[i+1];
    return fallback;
}

int main(int argc,char**argv){
    Learner learner(arg(argc,argv,"--db","strata11/data/learning.tsv"));
    const std::string mode=arg(argc,argv,"--mode","context");
    if(mode=="learn"){
        LearningRecord r;
        r.id=arg(argc,argv,"--id");
        r.assistant=arg(argc,argv,"--assistant","strata");
        r.question=arg(argc,argv,"--question");
        r.answer=arg(argc,argv,"--answer");
        if(r.question.empty()||r.answer.empty()) return 2;
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
