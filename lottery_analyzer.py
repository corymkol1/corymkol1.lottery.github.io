import csv
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

WEEKS_TO_ANALYZE = 12

EXPORT_FOLDER = Path("lottery_exports")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
}


# ============================================================
# GAME CONFIGURATION
# ============================================================

GAMES = {
    "1": {
        "name": "Powerball",
        "main_min": 1,
        "main_max": 69,
        "main_count": 5,
        "special_name": "Powerball",
        "special_min": 1,
        "special_max": 26,
    },

    "2": {
        "name": "Mega Millions",
        "main_min": 1,
        "main_max": 70,
        "main_count": 5,
        "special_name": "Mega Ball",
        "special_min": 1,
        "special_max": 24,
    },

    "3": {
        "name": "Florida Lotto",
        "main_min": 1,
        "main_max": 53,
        "main_count": 6,
        "special_name": None,
        "special_min": None,
        "special_max": None,
    },
}


# ============================================================
# DATE UTILITIES
# ============================================================

def get_cutoff_date():
    """
    Return the earliest date included in the analysis.
    """

    return datetime.now() - timedelta(
        weeks=WEEKS_TO_ANALYZE
    )


def date_is_in_range(draw_date):
    """
    Determine whether a draw occurred within
    the analysis period.
    """

    return draw_date >= get_cutoff_date()


# ============================================================
# POWERBALL DATA
# ============================================================

def get_powerball_results():
    """
    Download Powerball results from the
    New York State Open Data API.

    Returns:
        list of dictionaries
    """

    url = (
        "https://data.ny.gov/resource/"
        "d6yy-54nr.json"
    )

    cutoff = get_cutoff_date()

    cutoff_string = cutoff.strftime(
        "%Y-%m-%dT00:00:00.000"
    )

    params = {
        "$where": (
            f"draw_date >= '{cutoff_string}'"
        ),
        "$order": "draw_date DESC",
        "$limit": 100,
    }

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    draws = []

    for record in data:

        numbers_text = record.get(
            "winning_numbers"
        )

        if not numbers_text:
            continue

        numbers = [
            int(number)
            for number
            in numbers_text.split()
        ]

        # Powerball should contain
        # 5 white balls + 1 Powerball.
        if len(numbers) != 6:
            continue

        draw_date = datetime.fromisoformat(
            record["draw_date"]
            .replace("Z", "")
        )

        if not date_is_in_range(draw_date):
            continue

        draws.append({
            "date": draw_date,
            "main_numbers": numbers[:5],
            "special_number": numbers[5],
        })

    draws.sort(
        key=lambda draw: draw["date"],
        reverse=True,
    )

    return draws


# ============================================================
# MEGA MILLIONS DATA
# ============================================================

def get_mega_millions_results():
    """
    Download Mega Millions results from
    the New York State Open Data API.
    """

    url = (
        "https://data.ny.gov/resource/"
        "5xaw-6ayf.json"
    )

    cutoff = get_cutoff_date()

    cutoff_string = cutoff.strftime(
        "%Y-%m-%dT00:00:00.000"
    )

    params = {
        "$where": (
            f"draw_date >= '{cutoff_string}'"
        ),
        "$order": "draw_date DESC",
        "$limit": 100,
    }

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    draws = []

    for record in data:

        numbers_text = record.get(
            "winning_numbers"
        )

        mega_ball_text = record.get(
            "mega_ball"
        )

        if (
            not numbers_text
            or mega_ball_text is None
        ):
            continue

        main_numbers = [
            int(number)
            for number
            in numbers_text.split()
        ]

        if len(main_numbers) != 5:
            continue

        draw_date = datetime.fromisoformat(
            record["draw_date"]
            .replace("Z", "")
        )

        if not date_is_in_range(draw_date):
            continue

        draws.append({
            "date": draw_date,
            "main_numbers": main_numbers,
            "special_number": int(
                mega_ball_text
            ),
        })

    draws.sort(
        key=lambda draw: draw["date"],
        reverse=True,
    )

    return draws


# ============================================================
# FLORIDA LOTTO DATA
# ============================================================

def get_florida_lotto_results():
    """
    Download Florida Lotto results.

    Florida Lotto does not have the same simple
    public JSON API used for Powerball and
    Mega Millions here, so this parser reads
    recent Florida Lotto results from LotteryUSA.

    Only the six MAIN DRAW numbers are analyzed.
    Double Play numbers are ignored.
    """

    current_year = datetime.now().year

    url = (
        "https://www.lotteryusa.com/"
        "florida/lotto/year"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # Convert page to simplified text.
    text = soup.get_text(
        " ",
        strip=True,
    )

    cutoff = get_cutoff_date()

    draws = []

    # Look for dates such as:
    #
    # Wednesday, Sep 23, 2026
    #
    date_pattern = re.compile(
        r"(Monday|Tuesday|Wednesday|Thursday|"
        r"Friday|Saturday|Sunday),\s+"
        r"([A-Z][a-z]{2})\s+"
        r"(\d{1,2}),\s+"
        r"(\d{4})"
    )

    matches = list(
        date_pattern.finditer(text)
    )

    for index, match in enumerate(matches):

        date_text = " ".join([
            match.group(2),
            match.group(3) + ",",
            match.group(4),
        ])

        try:
            draw_date = datetime.strptime(
                date_text,
                "%b %d, %Y",
            )

        except ValueError:
            continue

        if draw_date < cutoff:
            continue

        # Determine the section belonging
        # to this drawing.
        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()

        else:
            end = len(text)

        section = text[start:end]

        # Look specifically between:
        #
        # Main Draw
        # ...
        # Double Play
        #
        main_match = re.search(
            r"Main Draw\s+(.*?)"
            r"(?:Double Play|Est\. jackpot)",
            section,
            re.DOTALL | re.IGNORECASE,
        )

        if not main_match:
            continue

        main_section = main_match.group(1)

        # Pull numeric values from Main Draw.
        possible_numbers = [
            int(value)
            for value in re.findall(
                r"\b\d{1,2}\b",
                main_section,
            )
        ]

        # Keep valid Florida Lotto numbers.
        possible_numbers = [
            number
            for number in possible_numbers
            if 1 <= number <= 53
        ]

        if len(possible_numbers) < 6:
            continue

        numbers = possible_numbers[:6]

        draws.append({
            "date": draw_date,
            "main_numbers": numbers,
            "special_number": None,
        })

    # Remove duplicates.
    unique_draws = {}

    for draw in draws:

        key = draw["date"].date()

        unique_draws[key] = draw

    draws = list(
        unique_draws.values()
    )

    draws.sort(
        key=lambda draw: draw["date"],
        reverse=True,
    )

    return draws


# ============================================================
# FREQUENCY ANALYSIS
# ============================================================

def build_frequency(
    counter,
    minimum,
    maximum,
):
    """
    Create a complete frequency table.

    Numbers that have never appeared are
    included with a frequency of zero.
    """

    frequency = []

    for number in range(
        minimum,
        maximum + 1,
    ):

        frequency.append({
            "number": number,
            "count": counter.get(
                number,
                0,
            ),
        })

    frequency.sort(
        key=lambda item: (
            item["count"],
            item["number"],
        )
    )

    return frequency


def analyze_game(
    draws,
    game,
):
    """
    Count main and special numbers.
    """

    main_counter = Counter()

    special_counter = Counter()

    for draw in draws:

        main_counter.update(
            draw["main_numbers"]
        )

        if (
            game["special_name"]
            and
            draw["special_number"]
            is not None
        ):
            special_counter.update([
                draw["special_number"]
            ])

    main_frequency = build_frequency(
        main_counter,
        game["main_min"],
        game["main_max"],
    )

    special_frequency = None

    if game["special_name"]:

        special_frequency = (
            build_frequency(
                special_counter,
                game["special_min"],
                game["special_max"],
            )
        )

    return {
        "main": main_frequency,
        "special": special_frequency,
    }


# ============================================================
# LOW / HIGH FREQUENCY HELPERS
# ============================================================

def get_least_common(frequency):
    """
    Return every number tied for the
    lowest frequency.
    """

    if not frequency:
        return []

    lowest_count = frequency[0]["count"]

    return [
        item
        for item in frequency
        if item["count"] == lowest_count
    ]


def get_most_common(frequency):
    """
    Return every number tied for the
    highest frequency.
    """

    if not frequency:
        return []

    highest_count = max(
        item["count"]
        for item in frequency
    )

    return [
        item
        for item in frequency
        if item["count"] == highest_count
    ]


# ============================================================
# DISPLAY DRAW HISTORY
# ============================================================

def display_draws(
    game,
    draws,
):
    print()

    print("=" * 72)
    print(
        f"{game['name'].upper()} "
        f"- LAST {WEEKS_TO_ANALYZE} WEEKS"
    )
    print("=" * 72)

    print(
        f"\nDrawings analyzed: "
        f"{len(draws)}"
    )

    print()

    print("DRAW HISTORY")
    print("-" * 72)

    for draw in draws:

        date_string = draw[
            "date"
        ].strftime(
            "%Y-%m-%d"
        )

        main = " ".join(
            f"{number:02}"
            for number
            in draw["main_numbers"]
        )

        if game["special_name"]:

            print(
                f"{date_string} | "
                f"{main} | "
                f"{game['special_name']}: "
                f"{draw['special_number']:02}"
            )

        else:

            print(
                f"{date_string} | "
                f"{main}"
            )


# ============================================================
# DISPLAY FREQUENCY TABLE
# ============================================================

def display_frequency_table(
    title,
    frequency,
):
    print()

    print(title)
    print("-" * 36)

    print(
        f"{'Number':>8} | "
        f"{'Times Drawn':>11}"
    )

    print("-" * 24)

    for item in frequency:

        print(
            f"{item['number']:>8} | "
            f"{item['count']:>11}"
        )


# ============================================================
# DISPLAY SUMMARY
# ============================================================

def display_summary(
    game,
    analysis,
):
    print()

    print("=" * 72)
    print("FREQUENCY ANALYSIS")
    print("=" * 72)

    main_frequency = analysis["main"]

    display_frequency_table(
        "MAIN NUMBERS - LEAST TO MOST COMMON",
        main_frequency,
    )

    least = get_least_common(
        main_frequency
    )

    most = get_most_common(
        main_frequency
    )

    print()

    print("=" * 72)
    print("MAIN NUMBER SUMMARY")
    print("=" * 72)

    print(
        "\nLeast common number(s):"
    )

    print(
        ", ".join(
            str(item["number"])
            for item in least
        )
    )

    print(
        f"Frequency: "
        f"{least[0]['count']} "
        f"time(s)"
    )

    print(
        "\nMost common number(s):"
    )

    print(
        ", ".join(
            str(item["number"])
            for item in most
        )
    )

    print(
        f"Frequency: "
        f"{most[0]['count']} "
        f"time(s)"
    )

    # Special-ball analysis
    if analysis["special"]:

        special_frequency = (
            analysis["special"]
        )

        print()

        print("=" * 72)

        print(
            f"{game['special_name'].upper()} "
            "ANALYSIS"
        )

        print("=" * 72)

        display_frequency_table(
            (
                f"{game['special_name']} "
                "- LEAST TO MOST COMMON"
            ),
            special_frequency,
        )

        least_special = (
            get_least_common(
                special_frequency
            )
        )

        most_special = (
            get_most_common(
                special_frequency
            )
        )

        print()

        print(
            f"Least common "
            f"{game['special_name']}(s):"
        )

        print(
            ", ".join(
                str(item["number"])
                for item
                in least_special
            )
        )

        print(
            f"Frequency: "
            f"{least_special[0]['count']} "
            f"time(s)"
        )

        print(
            f"\nMost common "
            f"{game['special_name']}(s):"
        )

        print(
            ", ".join(
                str(item["number"])
                for item
                in most_special
            )
        )

        print(
            f"Frequency: "
            f"{most_special[0]['count']} "
            f"time(s)"
        )


# ============================================================
# CSV FILE NAME
# ============================================================

def clean_filename(name):
    """
    Convert a game name into a safe file name.
    """

    return (
        name.lower()
        .replace(" ", "_")
    )


# ============================================================
# EXPORT DRAW HISTORY
# ============================================================

def export_draw_history(
    game,
    draws,
):
    EXPORT_FOLDER.mkdir(
        exist_ok=True
    )

    base_name = clean_filename(
        game["name"]
    )

    filename = (
        EXPORT_FOLDER
        / f"{base_name}_draws.csv"
    )

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.writer(file)

        header = [
            "Date",
        ]

        for position in range(
            1,
            game["main_count"] + 1,
        ):

            header.append(
                f"Number {position}"
            )

        if game["special_name"]:
            header.append(
                game["special_name"]
            )

        writer.writerow(
            header
        )

        for draw in draws:

            row = [
                draw["date"].strftime(
                    "%Y-%m-%d"
                )
            ]

            row.extend(
                draw["main_numbers"]
            )

            if game["special_name"]:
                row.append(
                    draw["special_number"]
                )

            writer.writerow(
                row
            )

    print(
        f"\nDraw history exported to:"
        f"\n{filename.resolve()}"
    )


# ============================================================
# EXPORT FREQUENCY ANALYSIS
# ============================================================

def export_frequency(
    game,
    analysis,
):
    EXPORT_FOLDER.mkdir(
        exist_ok=True
    )

    base_name = clean_filename(
        game["name"]
    )

    filename = (
        EXPORT_FOLDER
        / f"{base_name}_frequency.csv"
    )

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "Number",
            "Times Drawn",
            "Type",
            "Ranking",
        ])

        main_frequency = (
            analysis["main"]
        )

        least_main = {
            item["number"]
            for item
            in get_least_common(
                main_frequency
            )
        }

        most_main = {
            item["number"]
            for item
            in get_most_common(
                main_frequency
            )
        }

        for item in main_frequency:

            ranking = ""

            if item["number"] in least_main:
                ranking = "Least Common"

            if item["number"] in most_main:
                ranking = "Most Common"

            writer.writerow([
                item["number"],
                item["count"],
                "Main Number",
                ranking,
            ])

        if analysis["special"]:

            special_frequency = (
                analysis["special"]
            )

            least_special = {
                item["number"]
                for item
                in get_least_common(
                    special_frequency
                )
            }

            most_special = {
                item["number"]
                for item
                in get_most_common(
                    special_frequency
                )
            }

            for item in special_frequency:

                ranking = ""

                if (
                    item["number"]
                    in least_special
                ):
                    ranking = (
                        "Least Common"
                    )

                if (
                    item["number"]
                    in most_special
                ):
                    ranking = (
                        "Most Common"
                    )

                writer.writerow([
                    item["number"],
                    item["count"],
                    game["special_name"],
                    ranking,
                ])

    print(
        f"\nFrequency analysis exported to:"
        f"\n{filename.resolve()}"
    )


# ============================================================
# EXPORT MENU
# ============================================================

def export_menu(
    game,
    draws,
    analysis,
):
    while True:

        print()

        print("=" * 50)
        print("EXPORT OPTIONS")
        print("=" * 50)

        print(
            """
1. Export drawing history
2. Export frequency analysis
3. Export both
4. Return to main menu
"""
        )

        choice = input(
            "Select an option: "
        ).strip()

        if choice == "1":

            export_draw_history(
                game,
                draws,
            )

        elif choice == "2":

            export_frequency(
                game,
                analysis,
            )

        elif choice == "3":

            export_draw_history(
                game,
                draws,
            )

            export_frequency(
                game,
                analysis,
            )

        elif choice == "4":
            break

        else:

            print(
                "\nInvalid selection."
            )


# ============================================================
# DOWNLOAD GAME
# ============================================================

def download_game(game_choice):

    if game_choice == "1":

        print(
            "\nDownloading "
            "Powerball results..."
        )

        return (
            get_powerball_results()
        )

    if game_choice == "2":

        print(
            "\nDownloading "
            "Mega Millions results..."
        )

        return (
            get_mega_millions_results()
        )

    if game_choice == "3":

        print(
            "\nDownloading "
            "Florida Lotto results..."
        )

        return (
            get_florida_lotto_results()
        )

    return []


# ============================================================
# RUN ANALYSIS
# ============================================================

def run_game(game_choice):

    game = GAMES[
        game_choice
    ]

    draws = download_game(
        game_choice
    )

    if not draws:

        print(
            "\nNo drawings were found "
            "for the selected period."
        )

        return

    analysis = analyze_game(
        draws,
        game,
    )

    display_draws(
        game,
        draws,
    )

    display_summary(
        game,
        analysis,
    )

    export_menu(
        game,
        draws,
        analysis,
    )


# ============================================================
# MAIN MENU
# ============================================================

def display_main_menu():

    print()

    print("=" * 60)
    print("LOTTERY NUMBER FREQUENCY ANALYZER")
    print("=" * 60)

    print(
        f"Analysis Period: "
        f"Last {WEEKS_TO_ANALYZE} Weeks"
    )

    print(
        """
1. Powerball
2. Mega Millions
3. Florida Lotto
4. Exit
"""
    )


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():

    while True:

        display_main_menu()

        choice = input(
            "Select a lottery: "
        ).strip()

        if choice == "4":

            print(
                "\nProgram closed."
            )

            break

        if choice not in GAMES:

            print(
                "\nInvalid selection. "
                "Choose 1, 2, 3, or 4."
            )

            continue

        try:

            run_game(
                choice
            )

        except requests.RequestException as error:

            print(
                "\nUnable to download "
                "lottery data."
            )

            print(
                f"Network error: {error}"
            )

        except KeyboardInterrupt:

            print(
                "\n\nOperation cancelled."
            )

            break

        except Exception as error:

            print(
                "\nAn unexpected error "
                "occurred."
            )

            print(
                f"Error: {error}"
            )


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":
    main()