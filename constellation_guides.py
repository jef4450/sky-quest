"""Fixed, fact-gated text for a few familiar constellation patterns."""


GUIDES = (
    {
        "name": "Big Dipper",
        "anchors": ("Dubhe", "Merak", "Polaris"),
        "text": "Use the Big Dipper's pointer stars to find Polaris.",
    },
    {
        "name": "Orion",
        "anchors": ("Betelgeuse", "Rigel"),
        "text": "Find Orion's belt between Betelgeuse and Rigel.",
    },
    {
        "name": "Summer Triangle",
        "anchors": ("Vega", "Deneb", "Altair"),
        "text": "Vega, Deneb, and Altair mark the Summer Triangle.",
    },
    {
        "name": "Cassiopeia",
        "anchors": ("Schedar", "Caph", "Polaris"),
        "text": "Cassiopeia's W shape points toward Polaris.",
    },
    {
        "name": "Southern Cross",
        "anchors": ("Acrux", "Mimosa", "Gacrux"),
        "text": (
            "Acrux, Mimosa, and Gacrux form the Southern Cross; "
            "Hadar and Rigil Kentaurus point toward it."
        ),
    },
)


def applicable_guides(star_positions: dict[str, dict]) -> list[dict[str, str]]:
    """Return guides only when every named anchor is above the horizon."""
    return [
        {"name": guide["name"], "text": guide["text"]}
        for guide in GUIDES
        if all(
            star_positions.get(anchor, {}).get("above_horizon", False)
            for anchor in guide["anchors"]
        )
    ]
