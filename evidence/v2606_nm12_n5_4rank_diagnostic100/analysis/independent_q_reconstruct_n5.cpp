#include "ancf_kernel.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double PI=3.141592653589793238462643383279502884;
constexpr double L=13.12, D=0.028, SPAN=0.028, ACTIVE_END=5.94;
constexpr std::size_t NE=32, NS=5, NDOF=198;
constexpr std::array<double,NS> XS={0.594,1.782,2.970,4.158,5.346};
constexpr std::array<double,8> XI={-0.9602898564975363,-0.7966664774136267,-0.5255324099163290,-0.1834346424956498,0.1834346424956498,0.5255324099163290,0.7966664774136267,0.9602898564975363};
constexpr std::array<double,8> WG={0.1012285362903763,0.2223810344533745,0.3137066458778873,0.3626837833783620,0.3626837833783620,0.3137066458778873,0.2223810344533745,0.1012285362903763};
struct Row { unsigned long long ordinal; std::array<double,2*NS> raw; };
cfd_ancf::Model model(){
  cfd_ancf::Model m; m.length_m=L; m.diameter_m=D; m.elements=NE; m.slices=NS;
  m.slice_positions_m=std::vector<double>(XS.begin(),XS.end()); m.top_tension_N=1175.0;
  const double area=PI*D*D/4.0;
  m.youngs_modulus_Pa=7470000.0/area; m.material_density=1.845/area;
  m.section_property_mode=cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  m.explicit_EA_N=7470000.0; m.explicit_EI_Nm2=29.88;
  m.explicit_mass_per_length_kg_m=1.845; m.explicit_displaced_area_m2=area;
  m.fluid_density=1000.0; m.gravity=9.81; m.dt_s=4e-4;
  m.beta=0.25; m.gamma=0.5; m.max_newton=40; m.newton_tolerance=2e-10;
  m.gauss_order=3; m.mass_gauss_order=5;
  cfd_ancf::validate_model(m); return m;
}
void write_bin(const std::string& path,const std::vector<double>& v){
  std::ofstream o(path,std::ios::binary);
  const std::uint64_t n=v.size();
  o.write(reinterpret_cast<const char*>(&n),sizeof(n));
  o.write(reinterpret_cast<const char*>(v.data()),v.size()*sizeof(double));
  if(!o) throw std::runtime_error("write failed: "+path);
}
std::vector<double> integrate(const cfd_ancf::Model& m,const Row& row){
  std::array<std::array<double,3>,NS> f{};
  for(std::size_t i=0;i<NS;++i){f[i]={row.raw[2*i]/SPAN,row.raw[2*i+1]/SPAN,0.0};}
  std::vector<double> cuts={0.0,ACTIVE_END};
  cuts.insert(cuts.end(),XS.begin(),XS.end());
  for(std::size_t e=1;e<NE;++e){const double s=L*e/NE;if(s>0.0&&s<ACTIVE_END)cuts.push_back(s);}
  std::sort(cuts.begin(),cuts.end());
  cuts.erase(std::unique(cuts.begin(),cuts.end()),cuts.end());
  std::vector<double> q(NDOF,0.0);
  for(std::size_t k=0;k+1<cuts.size();++k){
    const double a=cuts[k],b=cuts[k+1];
    for(std::size_t g=0;g<8;++g){
      const double s=0.5*(a+b)+0.5*(b-a)*XI[g];
      std::array<double,3> fs{};
      if(s<=XS.front())fs=f.front();
      else if(s>=XS.back())fs=f.back();
      else {
        const auto right=std::upper_bound(XS.begin(),XS.end(),s);
        const std::size_t i=static_cast<std::size_t>(right-XS.begin())-1;
        const double t=(s-XS[i])/(XS[i+1]-XS[i]);
        for(int c=0;c<3;++c)fs[c]=(1-t)*f[i][c]+t*f[i+1][c];
      }
      cfd_ancf::Model point=m; point.slices=1; point.slice_positions_m={s};
      const auto H=cfd_ancf::mapping_H3(point);
      const double w=0.5*(b-a)*WG[g];
      for(std::size_t j=0;j<NDOF;++j)for(int c=0;c<3;++c)q[j]+=w*H(c,j)*fs[c];
    }
  }
  return q;
}
}
int main(int argc,char**argv){
  try{
    if(argc!=3)throw std::runtime_error("usage: independent_q_reconstruct_n5 input.csv output_dir");
    std::ifstream in(argv[1]); std::string line; const auto m=model();
    while(std::getline(in,line)){
      if(line.empty())continue;
      std::istringstream s(line); Row row{}; char comma;
      s>>row.ordinal;
      for(double& x:row.raw)s>>comma>>x;
      if(!s)throw std::runtime_error("bad csv row");
      write_bin(std::string(argv[2])+"/"+std::to_string(row.ordinal)+".bin",integrate(m,row));
    }
    return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
