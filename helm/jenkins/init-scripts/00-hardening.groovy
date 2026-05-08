import jenkins.model.Jenkins
import hudson.diagnosis.OldDataMonitor
import hudson.security.csrf.DefaultCrumbIssuer

def jenkins = Jenkins.instance

// Disable CLI-over-Remoting (legacy attack surface).
jenkins.descriptor("jenkins.CLI").get().setEnabled(false)

// No quiet period for triggered builds.
jenkins.setQuietPeriod(0)

// Disable the OldData monitor noise.
def oldData = jenkins.getAdministrativeMonitor(OldDataMonitor.class.name)
if (oldData != null) {
  oldData.disable(true)
}

// Enforce CSRF protection.
if (jenkins.getCrumbIssuer() == null) {
  jenkins.setCrumbIssuer(new DefaultCrumbIssuer(true))
}

jenkins.save()
