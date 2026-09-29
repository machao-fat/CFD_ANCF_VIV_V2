#include "../../v2606_nm13_n5_long10s_configuration/source/ancf_kernel.hpp"
#include <fstream>
#include <iostream>
#include <vector>
#include <cmath>
#include <sstream>
#include <cstdint>
#include <string>

static cfd_ancf::Model model() {
  cfd_ancf::Model m; m.length_m=13.12; m.diameter_m=.028; m.inner_diameter_m=0;
  m.elements=32; m.slices=5; m.slice_positions_m={.594,1.782,2.970,4.158,5.346};
  m.top_tension_N=1175.; const double A=M_PI*.028*.028/4.;
  m.section_property_mode=cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  m.explicit_EA_N=7470000.; m.explicit_EI_Nm2=29.88; m.explicit_mass_per_length_kg_m=1.845;
  m.explicit_displaced_area_m2=A; m.youngs_modulus_Pa=7470000./A; m.material_density=1.845/A;
  m.fluid_density=1000.; m.gravity=9.81; m.dt_s=4e-4; m.beta=.25; m.gamma=.5;
  m.max_newton=40; m.newton_tolerance=2e-10; m.gauss_order=3; m.mass_gauss_order=5;
  cfd_ancf::SpanwiseHydrodynamicRegion r; r.s_min_m=0; r.s_max_m=13.12;
  r.added_mass_per_length_kg_m={.616,.616,0}; r.linear_damping_per_length_Ns_m2={0,0,0};
  m.hydrodynamic_regions={r}; cfd_ancf::validate_model(m); return m;
}
static std::vector<double> q0(const char* path) {
  std::ifstream f(path); std::string line; bool selected=false;
  while(std::getline(f,line)) { if(line.rfind("CASE REF_NE32 32 7470000",0)==0){selected=true;continue;} if(selected&&line.rfind("Q 198 ",0)==0){std::istringstream ss(line);std::string tag;int n;ss>>tag>>n;std::vector<double> q(n);for(double& x:q)ss>>x;return q;} }
  throw std::runtime_error("q0 not found");
}
static void write_matrix(const char* path,const cfd_ancf::Matrix& a){std::ofstream f(path,std::ios::binary);std::uint64_t n=a.rows;f.write((char*)&n,8);f.write((char*)a.data.data(),a.data.size()*8);}
int main(int argc,char**argv){ if(argc!=3)return 2; auto m=model(); auto q=q0(argv[1]); auto st=cfd_ancf::make_reference_state(m); std::vector<double> ff; cfd_ancf::Matrix K; cfd_ancf::internal_force_tangent(q,m,ff,K); write_matrix(argv[2],st.mass); write_matrix((std::string(argv[2])+".K").c_str(),K); std::ofstream fq((std::string(argv[2])+".q0").c_str(),std::ios::binary); fq.write((char*)q.data(),q.size()*8); std::cout<<"ndof "<<m.ndof()<<" mass "<<st.mass.rows<<" tangent "<<K.rows<<"\n"; }
