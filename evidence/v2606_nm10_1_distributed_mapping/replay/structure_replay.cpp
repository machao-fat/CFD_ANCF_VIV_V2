#include "distributed_force_mapping.hpp"
#include "structure_state_evaluator.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr double PI = 3.141592653589793238462643383279502884;
constexpr double LENGTH = 13.12, D = 0.028, DT = 4e-4, UNIT_SPAN = 0.028;
constexpr std::size_t ELEMENTS = 32, NSLICES = 3;
const std::array<double, NSLICES> S = {0.99, 2.97, 4.95};

cfd_ancf::Model make_model() {
  cfd_ancf::Model m; m.length_m = LENGTH; m.diameter_m = D; m.inner_diameter_m = 0.0;
  m.elements = ELEMENTS; m.slices = NSLICES; m.slice_positions_m.assign(S.begin(), S.end());
  m.top_tension_N = 1175.0; const double area = PI * D * D / 4.0;
  m.youngs_modulus_Pa = 7470000.0 / area; m.material_density = 1.845 / area;
  m.section_property_mode = cfd_ancf::SectionPropertyMode::ExplicitSectionProperties;
  m.explicit_EA_N = 7470000.0; m.explicit_EI_Nm2 = 29.88;
  m.explicit_mass_per_length_kg_m = 1.845; m.explicit_displaced_area_m2 = area;
  m.fluid_density = 1000.0; m.gravity = 9.81; m.dt_s = DT; m.beta = 0.25; m.gamma = 0.5;
  m.max_newton = 40; m.newton_tolerance = 2e-10; m.gauss_order = 3; m.mass_gauss_order = 5;
  cfd_ancf::validate_model(m); return m;
}

std::vector<double> load_q0(const std::string& path) {
  std::ifstream in(path); if (!in) throw std::runtime_error("q0 missing"); std::string line;
  bool selected = false;
  while (std::getline(in, line)) {
    if (line.rfind("CASE REF_NE32 32 7470000", 0) == 0) { selected = true; continue; }
    if (selected && line.rfind("Q ", 0) == 0) {
      std::istringstream row(line); std::string tag; std::size_t n; row >> tag >> n;
      std::vector<double> q(n); for (double& x : q) row >> x; return q;
    }
  }
  throw std::runtime_error("q0 reference case missing");
}

double dot(const std::vector<double>& a, const std::vector<double>& b) {
  double r = 0.0; for (std::size_t i = 0; i < a.size(); ++i) r += a[i] * b[i]; return r;
}

struct Row { int window = 0; std::array<std::array<double, 2>, NSLICES> raw{}; };
std::vector<Row> read_rows(const std::string& path) {
  std::ifstream in(path); if (!in) throw std::runtime_error("force history missing");
  std::vector<Row> rows; std::string line;
  while (std::getline(in, line)) {
    if (line.empty()) continue; std::istringstream s(line); Row r; char comma;
    s >> r.window; for (auto& force : r.raw) s >> comma >> force[0] >> comma >> force[1];
    if (!s) throw std::runtime_error("force history row malformed"); rows.push_back(r);
  }
  return rows;
}

std::vector<double> constant_q(const cfd_ancf::Model& model,
    const std::array<std::array<double, 2>, NSLICES>& raw) {
  static constexpr std::array<double, 8> xi = {-0.9602898565,-0.7966664774,-0.5255324099,-0.1834346425,0.1834346425,0.5255324099,0.7966664774,0.9602898565};
  static constexpr std::array<double, 8> w = {0.1012285363,0.2223810345,0.3137066459,0.3626837834,0.3626837834,0.3137066459,0.2223810345,0.1012285363};
  std::vector<double> q(model.ndof(), 0.0); const double Le = model.length_m / model.elements;
  for (std::size_t i=0;i<NSLICES;++i) {
    const double left=1.98*i, right=left+1.98; const std::array<double,3> f={raw[i][0]/UNIT_SPAN,raw[i][1]/UNIT_SPAN,0.0};
    std::vector<double> b{left,right}; for(std::size_t e=1;e<model.elements;++e){double x=Le*e;if(x>left&&x<right)b.push_back(x);} std::sort(b.begin(),b.end());
    for(std::size_t k=0;k+1<b.size();++k) for(std::size_t g=0;g<8;++g){double s=.5*(b[k]+b[k+1])+.5*(b[k+1]-b[k])*xi[g]; cfd_ancf::Model p=model;p.slices=1;p.slice_positions_m={s};auto H=cfd_ancf::mapping_H3(p);double a=.5*(b[k+1]-b[k])*w[g];for(std::size_t j=0;j<model.ndof();++j)for(std::size_t c=0;c<3;++c)q[j]+=a*H(c,j)*f[c];}
  } return q;
}

nm10_mapping::MappingConfig dcfg(){nm10_mapping::MappingConfig c;c.mode=nm10_mapping::MappingMode::PiecewiseLinearDistributed;c.endpoint_policy=nm10_mapping::EndpointPolicy::NearestConstant;c.active_s_min_m=0;c.active_s_max_m=5.94;c.unit_span_m=UNIT_SPAN;return c;}

void replay(const std::string& mode, const std::vector<Row>& rows, const std::vector<double>& q0, const cfd_ancf::Model& model, const std::string& outpath){
  cfd_ancf::State state=cfd_ancf::make_reference_state(model);state.q=q0;state.base_load=cfd_ancf::static_base_load(model);std::ofstream out(outpath);if(!out)throw std::runtime_error("output missing");out<<std::setprecision(17);double cw=0, caw=0;
  for(const auto& row:rows){auto qbefore=state.q;std::vector<double> qforce; cfd_ancf::StepDiagnostics d;
    if(mode=="M1") {
      // The frozen public kernel exposes transient advance for legacy point
      // and V2 piecewise-linear inputs.  M1 remains an offline load reference;
      // its q/v trajectory is intentionally not fabricated through M2.
      throw std::runtime_error("M1 structure trajectory requires a generalized-force advance API; load/power replay is recorded separately");
    } else {
      std::vector<double> p(S.begin(),S.end()); std::vector<std::array<double,3>> raw(NSLICES);
      for(std::size_t i=0;i<NSLICES;++i)raw[i]={row.raw[i][0],row.raw[i][1],0.0};
      nm10_mapping::MappingConfig c=dcfg();
      if(mode=="M0") {
        c.mode=nm10_mapping::MappingMode::LegacyPointLumped; c.legacy_tributary_length_m=1.98;
        const auto mapped=nm10_mapping::assemble(model,p,raw,c); qforce=mapped.generalized_force;
        std::vector<double> strip(3*NSLICES,0.0);
        for(std::size_t i=0;i<NSLICES;++i)for(std::size_t cc=0;cc<3;++cc)strip[3*i+cc]=raw[i][cc]/UNIT_SPAN*1.98;
        d=cfd_ancf::advance(state,model,strip);
      } else {
        const auto mapped=nm10_mapping::assemble(model,p,raw,c); qforce=mapped.generalized_force;
        cfd_ancf::SpanwiseLoadInput input; input.mode=cfd_ancf::SpanwiseLoadReconstruction::PiecewiseLinearDistributed; input.endpoint_policy=cfd_ancf::SpanwiseEndpointPolicy::NearestConstant; input.active_region={0.0,5.94}; input.samples.resize(NSLICES);
        for(std::size_t i=0;i<NSLICES;++i){input.samples[i].s_m=S[i];input.samples[i].line_force_Npm=mapped.line_force_Npm[i];}
        d=cfd_ancf::advance(state,model,input);
      }
    }
    if(!d.converged||!cfd_ancf::finite(state))throw std::runtime_error("advance failed");std::vector<double> dq(state.q.size());for(std::size_t i=0;i<dq.size();++i)dq[i]=state.q[i]-qbefore[i];double sw=dot(dq,qforce);cw+=sw;caw+=std::abs(sw);out<<"{\"mode\":\""<<mode<<"\",\"window\":"<<row.window<<",\"Q_norm\":"<<std::sqrt(dot(qforce,qforce))<<",\"Q\":[";for(std::size_t i=0;i<qforce.size();++i){if(i)out<<',';out<<qforce[i];}out<<"],\"power\":"<<dot(state.qdot,qforce)<<",\"step_work\":"<<sw<<",\"cumulative_work\":"<<cw<<",\"cumulative_abs_work\":"<<caw;
    for(const auto& item:std::array<std::pair<const char*,double>,4>{{{"D099",.99},{"D297",2.97},{"D495",4.95},{"D594",5.94}}}){auto e=nm10_mapping::evaluateStructureState(model,item.second,state.q,q0,state.qdot,state.qddot);out<<",\""<<item.first<<"_x\":"<<e.displacement_m[0]<<",\""<<item.first<<"_y\":"<<e.displacement_m[1];}out<<"}\n";
  }
}

void mapping_only_m1(const std::vector<Row>& rows, const cfd_ancf::Model& model,
                     const std::string& outpath) {
  std::ofstream out(outpath); if (!out) throw std::runtime_error("M1 output missing");
  out << std::setprecision(17);
  for (const auto& row : rows) {
    const auto q = constant_q(model, row.raw);
    out << "{\"mode\":\"M1\",\"window\":" << row.window << ",\"Q_norm\":"
        << std::sqrt(dot(q, q)) << ",\"Q\":[";
    for (std::size_t i = 0; i < q.size(); ++i) { if (i) out << ','; out << q[i]; }
    out << "],\"trajectory\":\"LOAD_ONLY\"}\n";
  }
}
} // namespace

int main(int argc,char**argv){try{if(argc!=4)throw std::runtime_error("usage: replay force.csv q0 output-prefix");auto m=make_model();auto rows=read_rows(argv[1]);auto q0=load_q0(argv[2]);replay("M0",rows,q0,m,std::string(argv[3])+"_m0.jsonl");mapping_only_m1(rows,m,std::string(argv[3])+"_m1.jsonl");replay("M2",rows,q0,m,std::string(argv[3])+"_m2.jsonl");std::ofstream note(std::string(argv[3])+"_m1_trajectory_status.json");note<<"{\"status\":\"NOT_EXECUTED\",\"reason\":\"frozen core has no public generalized-force advance API; M1 remains load/power offline reference\"}\n";std::cout<<"STRUCTURE_REPLAY_M0_M2=PASS rows="<<rows.size()<<" M1=LOAD_ONLY\n";return 0;}catch(const std::exception&e){std::cerr<<"REPLAY_FATAL: "<<e.what()<<'\n';return 2;}}
