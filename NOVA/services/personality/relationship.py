"""
Stores relationship state between NOVA and its user.
"""


class Relationship:

    def __init__(self):

        self.level = 1

        self.trust = 100

        self.shared_projects = []

    def add_project(self, name):

        if name not in self.shared_projects:

            self.shared_projects.append(name)

    def context(self):

        projects = ", ".join(self.shared_projects)

        return f"""
Relationship Level: {self.level}
Trust Score: {self.trust}

Projects:
{projects if projects else "None"}
"""