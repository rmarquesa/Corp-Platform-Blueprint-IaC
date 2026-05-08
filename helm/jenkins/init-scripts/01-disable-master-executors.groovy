import jenkins.model.Jenkins

Jenkins.instance.setNumExecutors(0)
Jenkins.instance.save()
