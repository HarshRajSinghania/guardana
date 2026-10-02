"""Read the files a profile names, through the loaders the runs use.

`config validate`, `config explain` and `doctor --profile` share this, so none of them
can call a profile valid whose contracts, calibrations or rule paths a run then refuses.
"""

from dataclasses import dataclass

from guardana.cli._contracts import ReadContracts, contract_paths, read_contracts
from guardana.cli._rules_loading import rule_path_problems
from guardana.core.manifest.build import ProfileCalibrations, read_profile_calibrations
from guardana.core.profile import Profile


@dataclass(frozen=True, slots=True)
class ProfileFiles:
    """What the files a profile names contain, and every reason a run would refuse them."""

    contracts: ReadContracts
    calibrations: ProfileCalibrations
    rule_paths: tuple[str, ...]
    """One sentence per `rules.paths` entry a run would load nothing from."""

    @property
    def problems(self) -> tuple[str, ...]:
        """Every problem, contracts first, then calibrations, then rule paths."""
        return (*self.contracts.problems, *self.calibrations.problems, *self.rule_paths)

    def loaded_contracts(self) -> list[dict[str, object]]:
        """Describe each contract that loaded: its name, file, size and system."""
        return [
            {
                "name": contract.name,
                "source": contract.source,
                "assertions": len(contract.assertions),
                "ai_system": contract.applies_to.ai_system,
            }
            for contract in self.contracts.contracts
        ]

    def calibrated_evaluators(self) -> dict[str, str]:
        """Name the file each calibrated evaluator's measurement came from."""
        return {
            evaluator: str(path) for evaluator, path in sorted(self.calibrations.sources.items())
        }


def read_profile_files(profile: Profile) -> ProfileFiles:
    """Load every contract, calibration and rule path the profile names, collecting problems."""
    return ProfileFiles(
        contracts=read_contracts(contract_paths(profile, [])),
        calibrations=read_profile_calibrations(profile),
        rule_paths=tuple(rule_path_problems(profile)),
    )
