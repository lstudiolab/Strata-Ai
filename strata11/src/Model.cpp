#include "strata11/Model.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <random>
namespace strata {
Model::Model(ModelConfig c):c_(c){init();}
void Model::init(){
 std::mt19937 g(42); std::normal_distribution<float>d(0,.03f);
 e_.resize(c_.vocab*c_.embedding); w_.resize(c_.embedding*c_.hidden);
 b_.assign(c_.hidden,0); o_.resize(c_.hidden*c_.vocab); ob_.assign(c_.vocab,0);
 for(float&x:e_)x=d(g); for(float&x:w_)x=d(g); for(float&x:o_)x=d(g);
}
std::vector<float> Model::forward(const std::vector<unsigned char>&t)const{
 std::vector<float>h(c_.hidden,0); if(t.empty())return h; float inv=1.f/t.size();
 for(auto x:t)for(int j=0;j<c_.embedding;j++)for(int k=0;k<c_.hidden;k++)
   h[k]+=e_[x*c_.embedding+j]*w_[j*c_.hidden+k]*inv;
 for(float&x:h)x=std::max(0.f,x);
 for(int k=0;k<c_.hidden;k++)h[k]+=b_[k];
 std::vector<float>z(c_.vocab);
 for(int v=0;v<c_.vocab;v++){z[v]=ob_[v];for(int k=0;k<c_.hidden;k++)z[v]+=h[k]*o_[k*c_.vocab+v];}
 return z;
}
float Model::train(const std::vector<unsigned char>&tokens,float lr){
 if(tokens.size()<2)return 0; float loss=0;
 for(size_t p=1;p<tokens.size();p++){
  size_t begin=p>size_t(c_.context)?p-c_.context:0;
  std::vector<unsigned char>ctx(tokens.begin()+begin,tokens.begin()+p);
  auto h=forward(ctx); float mx=*std::max_element(h.begin(),h.end()),sum=0;
  for(float&x:h){x=std::exp(std::min(20.f,x-mx));sum+=x;} for(float&x:h)x/=sum;
  int y=tokens[p]; loss-=std::log(std::max(h[y],1e-7f));
  std::vector<float>dh(c_.hidden,0);
  for(int v=0;v<c_.vocab;v++){float dz=h[v]-(v==y);ob_[v]-=lr*dz;
   for(int k=0;k<c_.hidden;k++){auto i=k*c_.vocab+v;dh[k]+=dz*o_[i];o_[i]-=lr*dz*std::max(0.f,h[k]);}}
  for(int k=0;k<c_.hidden;k++){float g=dh[k];b_[k]-=lr*g;float inv=1.f/ctx.size();
   for(auto x:ctx)for(int j=0;j<c_.embedding;j++){auto i=j*c_.hidden+k;float old=w_[i];
    w_[i]-=lr*g*e_[x*c_.embedding+j]*inv;e_[x*c_.embedding+j]-=lr*g*old*inv;}}
 }
 return loss/(tokens.size()-1);
}
unsigned char Model::sample(const std::vector<float>&z,float temp)const{
 static thread_local std::mt19937 g(std::random_device{}()); float mx=*std::max_element(z.begin(),z.end()),sum=0;
 std::vector<float>p(z.size());for(size_t i=0;i<z.size();i++){p[i]=std::exp((z[i]-mx)/std::max(.05f,temp));sum+=p[i];}
 std::uniform_real_distribution<float>d(0,sum),pick(0,1);float r=d(g);for(size_t i=0;i<p.size();i++){r-=p[i];if(r<=0)return (unsigned char)i;}return 0;
}
std::string Model::generate(const std::string&prompt,int n,float temp)const{
 std::vector<unsigned char>t(prompt.begin(),prompt.end());size_t start=t.size();
 for(int i=0;i<n;i++){size_t b=t.size()>size_t(c_.context)?t.size()-c_.context:0;std::vector<unsigned char>x(t.begin()+b,t.end());t.push_back(sample(forward(x),temp));}
 return std::string(t.begin()+start,t.end());
}
bool Model::save(const std::string&p)const{std::ofstream f(p,std::ios::binary);if(!f)return false;f.write((char*)&c_,sizeof(c_));auto w=[&](auto&v){size_t n=v.size();f.write((char*)&n,sizeof(n));f.write((char*)v.data(),n*sizeof(float));};w(e_);w(w_);w(b_);w(o_);w(ob_);return !!f;}
bool Model::load(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)return false;f.read((char*)&c_,sizeof(c_));auto r=[&](auto&v){size_t n;f.read((char*)&n,sizeof(n));v.resize(n);f.read((char*)v.data(),n*sizeof(float));};r(e_);r(w_);r(b_);r(o_);r(ob_);return !!f;}
std::size_t Model::parameters()const{return e_.size()+w_.size()+b_.size()+o_.size()+ob_.size();}
}