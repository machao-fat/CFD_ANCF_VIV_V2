#include "ancf_kernel.hpp"
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>
#include <iostream>

namespace {
constexpr double PI=3.141592653589793238462643383279502884, L=13.12, D=0.028, SPAN=0.028;
constexpr std::size_t NE=32, NDOF=198;
struct Row { unsigned long long ordinal; std::array<double,6> raw; };
cfd_ancf::Model model() {
  cfd_ancf::Model m; m.length_m=L; m.diameter_m=D; m.elements=NE; m.slices=3;
  m.slice_positions_m={0.99,2.97,4.95}; m.top_tension_N=1175.0;
  const double a=PI*D*D/4.0; m.youngs_modulus_Pa=7470000.0/a; m.material_density=1.845/a;
  m.section_property_mode=cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  m.explicit_EA_N=7470000.0; m.explicit_EI_Nm2=29.88; m.explicit_mass_per_length_kg_m=1.845;
  m.explicit_displaced_area_m2=a; m.fluid_density=1000.0; m.gravity=9.81; m.dt_s=4e-4;
  m.beta=0.25; m.gamma=0.5; m.max_newton=40; m.newton_tolerance=2e-10; m.gauss_order=3; m.mass_gauss_order=5;
  cfd_ancf::validate_model(m); return m;
}
void write_bin(const std::string& p,const std::vector<double>& v){std::ofstream o(p,std::ios::binary);std::uint64_t n=v.size();o.write((char*)&n,sizeof(n));o.write((char*)v.data(),v.size()*sizeof(double));}
std::vector<double> integrate(const cfd_ancf::Model& m,const Row& row){
  const std::array<double,3> xs={0.99,2.97,4.95}; std::array<std::array<double,3>,3> f{};
  for(std::size_t i=0;i<3;++i){f[i][0]=row.raw[2*i]/SPAN;f[i][1]=row.raw[2*i+1]/SPAN;f[i][2]=0.0;}
  const double xelem=L/NE; const std::array<double,8> xi={-0.9602898564975363,-0.7966664774136267,-0.5255324099163290,-0.1834346424956498,0.1834346424956498,0.5255324099163290,0.7966664774136267,0.9602898564975363};
  const std::array<double,8> wg={0.1012285362903763,0.2223810344533745,0.3137066458778873,0.3626837833783620,0.3626837833783620,0.3137066458778873,0.2223810344533745,0.1012285362903763};
  std::vector<double> q(NDOF,0.0); std::vector<double> cuts={0.0,0.99,2.97,4.95,5.94};
  for(std::size_t e=1;e<NE;++e){double x=xelem*e;if(x>0.0&&x<5.94)cuts.push_back(x);} std::sort(cuts.begin(),cuts.end()); cuts.erase(std::unique(cuts.begin(),cuts.end()),cuts.end());
  for(std::size_t k=0;k+1<cuts.size();++k){double a=cuts[k],b=cuts[k+1];for(std::size_t g=0;g<8;++g){double s=.5*(a+b)+.5*(b-a)*xi[g];std::array<double,3> fs{};if(s<=xs[0])fs=f[0];else if(s>=xs[2])fs=f[2];else if(s<xs[1]){double t=(s-xs[0])/(xs[1]-xs[0]);for(int c=0;c<3;++c)fs[c]=(1-t)*f[0][c]+t*f[1][c];}else{double t=(s-xs[1])/(xs[2]-xs[1]);for(int c=0;c<3;++c)fs[c]=(1-t)*f[1][c]+t*f[2][c];}cfd_ancf::Model p=m;p.slices=1;p.slice_positions_m={s};auto H=cfd_ancf::mapping_H3(p);double w=.5*(b-a)*wg[g];for(std::size_t j=0;j<NDOF;++j)for(int c=0;c<3;++c)q[j]+=w*H(c,j)*fs[c];}}
  return q;
}
}
int main(int argc,char**argv){try{if(argc!=3)throw std::runtime_error("usage: q_reconstruct input.csv output_dir");std::ifstream in(argv[1]);std::string line;auto m=model();while(std::getline(in,line)){if(line.empty())continue;std::istringstream s(line);Row r{};char c;s>>r.ordinal;for(double&x:r.raw)s>>c>>x; if(!s)throw std::runtime_error("bad csv");write_bin(std::string(argv[2])+"/"+std::to_string(r.ordinal)+".bin",integrate(m,r));}return 0;}catch(const std::exception&e){return (std::cerr<<e.what()<<'\n',2);}}
