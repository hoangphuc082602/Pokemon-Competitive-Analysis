from python.services.team_analysis_service import (TeamService)

class TeamBuilder:
    def build_team(self,team):

        report = (
            TeamService.analyze_team(team)
        )
        return report