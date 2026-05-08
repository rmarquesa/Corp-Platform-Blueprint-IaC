import jenkins.model.Jenkins

def jenkins = Jenkins.instance
def protocols = new HashSet<>(jenkins.getAgentProtocols())
protocols.removeAll(["JNLP-connect", "JNLP2-connect", "CLI-connect"])
jenkins.setAgentProtocols(protocols)
jenkins.save()
