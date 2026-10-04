#pragma once
#include <cstdint>
#include <string>
#include <vector>
namespace strata {
struct ModelConfig { int vocab=256; int embedding=32; int hidden=128; int context=48; };
class Model {
public:
 explicit Model(ModelConfig c={});
 bool load(const std::string&);
 bool save(const std::string&) const;
 float train(const std::vector<unsigned char>&, float);
 std::string generate(const std::string&, int=160, float=0.8f) const;
 std::size_t parameters() const;
private:
 ModelConfig c_; std::vector<float> e_,w_,b_,o_,ob_;
 void init();
 std::vector<float> forward(const std::vector<unsigned char>&) const;
 unsigned char sample(const std::vector<float>&,float) const;
};
}