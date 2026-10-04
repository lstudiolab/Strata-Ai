#include "strata11/Model.hpp"
#include <algorithm>
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
static std::string arg(int ac,char**av,const std::string&n,const std::string&d=""){for(int i=1;i+1<ac;i++)if(std::string(av[i])==n)return av[i+1];return d;}
static std::string json_escape(const std::string&s){std::string o;for(char c:s){if(c=='\\')o+="\\\\";else if(c=='"')o+="\\\"";else if(c=='\n')o+="\\n";else if(c=='\r')o+="\\r";else if(c=='\t')o+="\\t";else o+=c;}return o;}
static std::string message(const std::string&b){
 auto p=b.find("\"message\"");if(p==std::string::npos)return{};p=b.find(':',p);if(p==std::string::npos)return{};p=b.find('"',p);if(p==std::string::npos)return{};++p;
 std::string o;bool e=false;for(;p<b.size();p++){char c=b[p];if(e){o+=c=='n'?'\n':c=='r'?'\r':c=='t'?'\t':c;e=false;continue;}if(c=='\\'){e=true;continue;}if(c=='"')break;o+=c;}return o;
}
static void reply(int fd,int code,const std::string&type,const std::string&body){
 std::ostringstream h;h<<"HTTP/1.1 "<<code<<" "<<(code==200?"OK":"Bad Request")<<"\r\nContent-Type: "<<type<<"\r\nContent-Length: "<<body.size()<<"\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n";
 auto s=h.str()+body;send(fd,s.data(),s.size(),0);
}
static std::string train_on_experience(Model&model,const std::string&prompt,const std::string&answer,const std::string&checkpoint){
 std::string experience="User: "+prompt+"\nStrata: "+answer+"\n";
 std::vector<unsigned char>t(experience.begin(),experience.end());
 float loss=model.train(t,0.0003f);model.save(checkpoint);
 std::ostringstream out;out<<"loss="<<loss<<" learned="<<t.size();return out.str();
}
static void client(int fd,Model&model,const std::string&checkpoint){
 char buf[16384];std::string r;ssize_t n;
 while(r.find("\r\n\r\n")==std::string::npos&&r.size()<131072){n=recv(fd,buf,sizeof(buf),0);if(n<=0)break;r.append(buf,n);}
 auto sep=r.find("\r\n\r\n");auto e=r.find("\r\n");std::string first=r.substr(0,e),body=sep==std::string::npos?"":r.substr(sep+4);
 if(first.rfind("GET /health",0)==0)reply(fd,200,"application/json","{\"status\":\"ok\",\"engine\":\"strata-cpp\",\"learning\":\"online\"}");
 else if(first.rfind("GET /api/models",0)==0)reply(fd,200,"application/json","{\"models\":[{\"id\":\"strata\",\"name\":\"Strata\",\"version\":\"1.0\",\"learning\":true},{\"id\":\"strata-beta\",\"name\":\"Strata 1.0\",\"version\":\"Beta\",\"learning\":true}]}");
 else if(first.rfind("POST /api/chat",0)==0){
  auto q=message(body);if(q.empty()){reply(fd,400,"application/json","{\"error\":\"Message is required.\"}");}
  else{
   std::string answer;{std::lock_guard<std::mutex>lock(model_mutex);answer=model.generate(q,180,.85f);if(answer.empty())answer="I am still learning from your prompts.";}
   std::thread([q,answer,&model,checkpoint]{std::lock_guard<std::mutex>lock(model_mutex);std::string info=train_on_experience(model,q,answer,checkpoint);std::cout<<"online learning: "<<info<<"\n";}).detach();
   reply(fd,200,"application/json","{\"message\":\""+json_escape(answer)+"\",\"model\":\"strata\",\"engine\":\"cpp\",\"learning\":true}");
  }
 } else if(first.rfind("GET /",0)==0){std::ifstream f("app/static/index.html");std::string x((std::istreambuf_iterator<char>(f)),{});reply(fd,200,"text/html; charset=utf-8",x);}
 else reply(fd,404,"application/json","{\"error\":\"Not found\"}");
 close(fd);
}
static int train_dataset(const std::string&dataset,const std::string&checkpoint,int epochs,float lr){
 std::ifstream f(dataset);if(!f){std::cerr<<"dataset not found: "<<dataset<<"\n";return 1;}Model m;std::string line;
 for(int ep=1;ep<=epochs;ep++){f.clear();f.seekg(0);double loss=0;size_t count=0;while(std::getline(f,line)){if(line.size()<2)continue;std::vector<unsigned char>t(line.begin(),line.end());loss+=m.train(t,lr);count++;}std::cout<<"epoch "<<ep<<" loss "<<(count?loss/count:0)<<"\n";m.save(checkpoint);}
 return 0;
}
int main(int ac,char**av){
 if(arg(ac,av,"--mode")=="train")return train_dataset(arg(ac,av,"--dataset","data/train.txt"),arg(ac,av,"--checkpoint","data/strata.model"),std::stoi(arg(ac,av,"--epochs","1")),std::stof(arg(ac,av,"--learning-rate","0.001")));
 Model model;auto checkpoint=arg(ac,av,"--model","data/strata.model");model.load(checkpoint);
 int port=std::stoi(arg(ac,av,"--port",std::getenv("PORT")?std::getenv("PORT"):"8000"));int s=socket(AF_INET,SOCK_STREAM,0);if(s<0)return 1;int yes=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
 sockaddr_in a{};a.sin_family=AF_INET;a.sin_addr.s_addr=INADDR_ANY;a.sin_port=htons(port);if(bind(s,(sockaddr*)&a,sizeof(a))<0)return 1;if(listen(s,32)<0)return 1;
 std::cout<<"Strata C++ online-learning engine: "<<model.parameters()<<" parameters, port "<<port<<"\n";
 while(true){int fd=accept(s,nullptr,nullptr);if(fd>=0)std::thread(client,fd,std::ref(model),checkpoint).detach();}
}