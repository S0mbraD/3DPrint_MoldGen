"""材料属性库 — 硅胶、聚氨酯、环氧树脂、注塑材料等"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MaterialProperties:
    name: str = "silicone"
    viscosity: float = 3000.0  # mPa·s
    density: float = 1.1  # g/cm³
    cure_time: float = 240.0  # min
    shrinkage: float = 0.001  # ratio
    max_pressure: float = 0.5  # MPa
    temperature: float = 25.0  # °C
    shore_hardness: str = "A30"
    color: str = "#e0e0e0"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "viscosity": self.viscosity,
            "density": self.density,
            "cure_time": self.cure_time,
            "shrinkage": self.shrinkage,
            "max_pressure": self.max_pressure,
            "temperature": self.temperature,
            "shore_hardness": self.shore_hardness,
        }

    @classmethod
    def silicone_shore_a10(cls) -> MaterialProperties:
        return cls(
            name="Silicone Shore A10",
            viscosity=2000.0, density=1.04, cure_time=360.0,
            shrinkage=0.001, max_pressure=0.3, temperature=25.0,
            shore_hardness="A10", color="#f0f0f0",
        )

    @classmethod
    def silicone_shore_a30(cls) -> MaterialProperties:
        return cls(
            name="Silicone Shore A30",
            viscosity=3500.0, density=1.08, cure_time=240.0,
            shrinkage=0.001, max_pressure=0.5, temperature=25.0,
            shore_hardness="A30", color="#e8e8e8",
        )

    @classmethod
    def silicone_shore_a50(cls) -> MaterialProperties:
        return cls(
            name="Silicone Shore A50",
            viscosity=8000.0, density=1.15, cure_time=180.0,
            shrinkage=0.002, max_pressure=0.8, temperature=25.0,
            shore_hardness="A50", color="#d0d0d0",
        )

    @classmethod
    def polyurethane(cls) -> MaterialProperties:
        return cls(
            name="Polyurethane",
            viscosity=1500.0, density=1.05, cure_time=30.0,
            shrinkage=0.003, max_pressure=1.0, temperature=25.0,
            shore_hardness="A60", color="#f5e6c8",
        )

    @classmethod
    def epoxy_resin(cls) -> MaterialProperties:
        return cls(
            name="Epoxy Resin",
            viscosity=500.0, density=1.15, cure_time=480.0,
            shrinkage=0.002, max_pressure=2.0, temperature=25.0,
            shore_hardness="D80", color="#fffde0",
        )

    @classmethod
    def abs_injection(cls) -> MaterialProperties:
        return cls(
            name="ABS Injection",
            viscosity=200.0, density=1.04, cure_time=0.5,
            shrinkage=0.005, max_pressure=80.0, temperature=230.0,
            shore_hardness="D95", color="#f0f0f0",
        )

    @classmethod
    def pp_injection(cls) -> MaterialProperties:
        return cls(
            name="PP Injection",
            viscosity=150.0, density=0.90, cure_time=0.3,
            shrinkage=0.015, max_pressure=60.0, temperature=220.0,
            shore_hardness="D70", color="#f8f8f8",
        )


MATERIAL_PRESETS: dict[str, MaterialProperties] = {
    "silicone_a10": MaterialProperties.silicone_shore_a10(),
    "silicone_a30": MaterialProperties.silicone_shore_a30(),
    "silicone_a50": MaterialProperties.silicone_shore_a50(),
    "polyurethane": MaterialProperties.polyurethane(),
    "epoxy_resin": MaterialProperties.epoxy_resin(),
    "abs_injection": MaterialProperties.abs_injection(),
    "pp_injection": MaterialProperties.pp_injection(),
}
