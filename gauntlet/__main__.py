"""python -m gauntlet          run the MCP server on stdio (what MCP clients launch)
python -m gauntlet eval     planted-error evaluation of the trust layer
python -m gauntlet sample <slug> [n]   CSV sheet for human citation/label review"""

import sys


def main(argv: list[str]) -> int:
    if not argv:
        from .tools import serve
        serve()
        return 0
    if argv[0] == "eval":
        from .evaluation import planted_errors
        res = planted_errors(verbose=True)
        print(f"\nPlanted errors caught: {res['caught']}/{res['planted']} (need {res['threshold']}); "
              f"controls {'ok' if res['controls_ok'] else 'FAILED'}")
        return 0 if res["passed"] else 1
    if argv[0] == "sample" and len(argv) >= 2:
        from .evaluation import sample_claims
        from .project import Project, projects_dir
        print(sample_claims(Project.open(projects_dir(), argv[1]), n=int(argv[2]) if len(argv) > 2 else 100))
        return 0
    print(__doc__)
    return 2


sys.exit(main(sys.argv[1:]))
