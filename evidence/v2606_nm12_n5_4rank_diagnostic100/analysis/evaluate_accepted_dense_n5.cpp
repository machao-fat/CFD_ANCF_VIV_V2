#include "ancf_kernel.hpp"
#include "structure_state_evaluator.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double PI=3.141592653589793238462643383279502884;
cfd_ancf::Model model(){
  cfd_ancf::Model m; m.length_m=13.12; m.diameter_m=.028; m.elements=32; m.slices=5;
  m.slice_positions_m={.594,1.782,2.970,4.158,5.346};m.top_tension_N=1175.0;
  const double area=PI*.028*.028/4;
  m.youngs_modulus_Pa=7470000.0/area;m.material_density=1.845/area;
  m.section_property_mode=cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  m.explicit_EA_N=7470000.0;m.explicit_EI_Nm2=29.88;m.explicit_mass_per_length_kg_m=1.845;
  m.explicit_displaced_area_m2=area;m.fluid_density=1000.0;m.gravity=9.81;m.dt_s=4e-4;
  m.beta=.25;m.gamma=.5;m.max_newton=40;m.newton_tolerance=2e-10;
  m.gauss_order=3;m.mass_gauss_order=5;cfd_ancf::validate_model(m);return m;
}
std::vector<double> read_bin(const std::string& path){
  std::ifstream in(path,std::ios::binary);if(!in)throw std::runtime_error("missing "+path);
  std::uint64_t n=0;in.read(reinterpret_cast<char*>(&n),sizeof(n));
  if(n!=198)throw std::runtime_error("unexpected vector size");
  std::vector<double> v(n);in.read(reinterpret_cast<char*>(v.data()),n*sizeof(double));
  if(!in)throw std::runtime_error("short vector");return v;
}
}
int main(int argc,char** argv){
  try{
    if(argc!=4)throw std::runtime_error("usage: evaluate_accepted_dense_n5 window_ordinal.csv runtime_dir output.csv");
    const std::string runtime=argv[2];
    std::ifstream list(argv[1]);std::ofstream out(argv[3]);if(!list||!out)throw std::runtime_error("file open failed");
    const auto m=model();const auto ref=read_bin(runtime+"/state_attempt_reference_q.bin");
    std::vector<double> grid;for(int i=0;i<=200;++i)grid.push_back(5.94*i/200.0);
    for(double s:{0.0,.594,1.188,1.782,2.376,2.970,3.564,4.158,4.752,5.346,5.94})grid.push_back(s);
    for(int e=0;e<=14;++e){double s=13.12*e/32.0;if(s<=5.94)grid.push_back(s);}
    std::sort(grid.begin(),grid.end());grid.erase(std::unique(grid.begin(),grid.end(),[](double a,double b){return std::abs(a-b)<1e-12;}),grid.end());
    out<<"window,s_m,Dx_m,Dy_m,Dnorm_m\n"<<std::setprecision(17);
    int window;unsigned ordinal;char comma;
    while(list>>window>>comma>>ordinal){
      char key[64];std::snprintf(key,sizeof(key),"/state_attempt_%04u",ordinal);
      const auto q=read_bin(runtime+key+std::string("_trial_q.bin"));
      const auto v=read_bin(runtime+key+std::string("_trial_v.bin"));
      const std::vector<double> a(q.size(),0.0);
      for(double s:grid){
        const auto state=nm10_mapping::evaluateStructureState(m,s,q,ref,v,a);
        const auto& d=state.displacement_m;
        out<<window<<','<<s<<','<<d[0]<<','<<d[1]<<','<<std::hypot(d[0],d[1])<<'\n';
      }
    }
    return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
