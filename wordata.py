from __future__ import annotations

import asyncio
import datetime
import gzip
import itertools
import json
import random
import string
from pathlib import Path
from typing import Counter, Iterable, Sequence, TypeVar

import platformdirs
import pyperclip
from rich.align import Align
from rich.bar import Bar
from rich.console import Group, RenderableType
from rich.panel import Panel as RichPanel
from rich.table import Table
from textual import events
from textual.app import App
from textual.layout import Layout
from textual.reactive import Reactive
from textual.views import DockView, GridView
from textual.widget import Widget
from textual.widgets import Button, ButtonPressed, Header
from textual.widgets._button import ButtonRenderable

BASE_DIR = Path(__file__).parent

IDLE = "bold white on rgb(130,130,130)"
EMPTY = "bold on rgb(18,18,18)"
ABSENT = 0
PRESENT = 1
CORRECT = 2
LETTER_STATUS = {
    ABSENT: "bold white on rgb(58,58,58)",
    PRESENT: "bold white on rgb(181,159,59)",
    CORRECT: "bold white on rgb(83,141,78)",
}
BLOCKS = {ABSENT: "⬛", PRESENT: "🟨", CORRECT: "🟩"}
INITIAL_STATS = {
    "played": 0,
    "stats": [0, 0, 0, 0, 0, 0],
    "current_streak": 0,
    "max_streak": 0,
}
TIME_LIMIT = 183
##SEED_DATE = datetime.datetime.combine(datetime.datetime(2021, 6, 19), datetime.time())
##STATS_JSON = Path(platformdirs.user_data_dir("wordle")) / ".stats.json"
##STATS_JSON.parent.mkdir(exist_ok=True, parents=True)
with BASE_DIR.joinpath("La.gz").open("rb") as laf, BASE_DIR.joinpath("Ta.gz").open(
    "rb"
) as taf:
    La: list[str] = json.loads(gzip.decompress(laf.read()))
    Ta: list[str] = json.loads(gzip.decompress(taf.read()))

# Override the La array with data-related words. It's only the words in the
# La array that are picked as solutions.
La = ["array",
      "areas",
      "chart",
      "count",
      "covid",
      "datum",
      "edges",
      "empty",
      "erase",
      "error",
      "field",
      "focus",
      "graph",
      "group",
      "index",
      "label",
      "lines",
      "marks",
      "model",
      "mongo",
      "nodes",
      "nosql",
      "pivot",
      "plots",
      "point",
      "power",
      "query",
      "round",
      "rules",
      "scale",
      "slice",
      "slope",
      "speak",
      "store",
      "table",
      "trend",
      "value",
      "wedge",
      "write"
    ]

T = TypeVar("T")


def partition(l: Iterable[T], size: int) -> Iterable[Sequence[T]]:
    it = iter(l)
    return iter(lambda: tuple(itertools.islice(it, size)), ())


##def calculate_eta(target_date: datetime.datetime) -> str | None:
##    """Print a human-readable ETA to the next wordle"""
##    units = [3600, 60, 1]
##    now = datetime.datetime.now()
##    dt = (target_date - now).total_seconds()
##    if dt <= 0:
##        return None
##    digits = []
##    for unit in units:
##        digits.append("%02d" % int(dt // unit))
##        dt %= unit
##    return f'[green]{":".join(digits)}[/green]'


class CountdownHeader(Header):
    def __init__(self, time_limit) -> None:
        super().__init__()
        self.time_left = time_limit
        self.max_time = time_limit
        self.winning_time = 0

    # Override the clock function to implement a countdown timer.
    def get_clock(self) -> str:
        if self.winning_time >0:
            return f'[yellow]{"Win:%d" % self.winning_time}[/yellow]'
        if (self.time_left <= 0):
            return f'[red]{"0:00"}[/red]'
        self.time_left = self.time_left - 1
        return f'[green]{"%(minutes)d:%(seconds)02d" % {"minutes":int(self.time_left/60),"seconds":self.time_left % 60}}[/green]'

    def stop_clock(self) -> None:
        self.winning_time = int(self.max_time - self.time_left)
        
        
class GameStats(Widget):
    def __init__(self, stats: dict) -> None:
        super().__init__()
        self.stats = stats

    def render(self) -> RenderableType:
        total_played = self.stats["played"]
        total_win = sum(self.stats["stats"])
        num_guesses = (
            len(self.stats["last_guesses"][0]) // 5 if self.stats["last_result"] else 0
        )
        data = {
            "Played": total_played,
            "Win %": round(total_win / total_played * 100, 1) if total_played else 0,
            "Current Streak": self.stats.get("current_streak", 0),
            "Max Streak": self.stats.get("max_streak", 0),
        }
        table = Table(*data.keys())
        table.add_row(*map(str, data.values()))
        bars = Table.grid("idx", "bar", padding=(0, 1))
        for i, value in enumerate(self.stats["stats"], 1):
            bars.add_row(
                str(i),
                Bar(
                    max(self.stats["stats"]),
                    0,
                    value,
                    color="rgb(83,141,78)"
                    if i == num_guesses and self.stats["last_result"]
                    else "rgb(58,58,58)",
                ),
            )
        render_group = Group(table, bars)
        return RichPanel(render_group, title="Stats")


class GameMessage(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.timer = None

    content: Reactive[str] = Reactive("")

##    def show_eta(self, target: datetime.datetime) -> None:
##        self.target_date = target
##        self.timer = self.set_interval(1, self.refresh)
##
##    async def clear_eta(self) -> None:
##        if self.timer is not None:
##            await self.timer.stop()
##            self.timer = None

    def render(self) -> RenderableType:
        renderable = self.content
##        if self.timer is not None:
##            eta = calculate_eta(self.target_date)
##            if eta is None:
##                self._child_tasks.add(asyncio.create_task(self.clear_eta()))
##            else:
##                renderable += f"\n\nNext wordle: {eta}"
        renderable = Align.center(renderable, vertical="middle")
        return RichPanel(renderable, title="Message")


class Letter(Widget):
    label: Reactive[RenderableType] = Reactive("")
    status: Reactive[int | None] = Reactive(None)

    def __init__(self, name: str, clickable: bool = False):
        super().__init__(name)
        self.name = name
        self.label = name
        self.clickable = clickable
        self.style = IDLE if clickable else EMPTY

    def render(self) -> RenderableType:
        return ButtonRenderable(
            self.label,
            self.style if self.status is None else LETTER_STATUS[self.status],
        )

    async def on_click(self, event: events.Click) -> None:
        event.prevent_default().stop()
        if self.clickable:
            await self.emit(ButtonPressed(self))


class GuessView(GridView):
    COLUMN_SIZE = 5
    ROW_SIZE = 6

    def __init__(self, layout: Layout = None, name: str | None = None) -> None:
        super().__init__(layout, name)
        self.slots = [Letter("") for _ in range(self.COLUMN_SIZE * self.ROW_SIZE)]
        self.current = 0

    def reset(self) -> None:
        self.slots = [Letter("") for _ in range(self.COLUMN_SIZE * self.ROW_SIZE)]
        self.current = 0
        
    @property
    def current_guess(self) -> list[Letter]:
        start = self.current // self.COLUMN_SIZE * self.COLUMN_SIZE
        return self.slots[start : start + self.COLUMN_SIZE]

    @property
    def current_word(self) -> list[str]:
        return [b.name for b in self.current_guess]

    @property
    def valid_guesses(self) -> list[Sequence[Letter]]:
        return list(
            partition(
                itertools.takewhile(lambda x: bool(x.name), self.slots),
                self.COLUMN_SIZE,
            )
        )

    def input_letter(self, letter: str) -> None:
        button = self.slots[self.current]
        if button.name:
            if self.current % self.COLUMN_SIZE == self.COLUMN_SIZE - 1:
                # The last letter is filled
                return
            self.current += 1
            button = self.slots[self.current]
        button.name = letter
        button.label = letter

    def backspace_letter(self) -> None:
        button = self.slots[self.current]
        if not button.name:
            if self.current % self.COLUMN_SIZE == 0:
                # the first letter
                return
            self.current -= 1
            button = self.slots[self.current]
        button.name = button.label = ""

    async def on_mount(self) -> None:
        self.grid.set_align("center", "center")
        self.grid.set_gap(1, 1)
        self.grid.add_column("column", repeat=self.COLUMN_SIZE, size=7)
        self.grid.add_row("row", size=3, repeat=self.ROW_SIZE)
        self.grid.place(*self.slots)

    def check_solution(self, solution: str) -> bool | None:
        word = self.current_word
        letters = self.current_guess
        self.log("Checking solution")
        if list(solution) == word:
            for b in letters:
                b.status = CORRECT
            return True
        counter = Counter(solution)
        for i, b in enumerate(letters):
            if solution[i] == b.name:
                counter[b.name] -= 1
                b.status = CORRECT
        for b in letters:
            if b.status == CORRECT:
                continue
            if counter.get(b.name, 0) <= 0:
                b.status = ABSENT
            else:
                counter[b.name] -= 1
                b.status = PRESENT

        if self.current < self.COLUMN_SIZE * self.ROW_SIZE - 1:
            self.current += 1
        else:
            return False


class KeyboardRow(GridView):
    def __init__(
        self, letters: Iterable[str], layout: Layout = None, name: str | None = None
    ) -> None:
        super().__init__(layout=layout, name=name)
        self.children = list(letters)

    async def on_mount(self) -> None:
        self.grid.set_align("center", "center")
        self.grid.set_gap(1, 1)
        self.grid.add_column("column", repeat=len(self.children), size=7)
        self.grid.add_row("row", size=3)
        self.grid.place(*self.children)


class WordleApp(App):
    KEYBOARD = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]

    def on_key(self, event: events.Key) -> None:
        if self.result is not None:
            if event.key == "c":
                self.copy_result()
            if event.key == "r":
                self.reset()
            return
        if self.header.time_left <= 0:
            self.message.content = "Time's up"
        else:
            self.message.content = ""
        if event.key in string.ascii_letters:
            self.guess.input_letter(event.key.upper())
        elif event.key == "enter":
            self.check_input()
        elif event.key == "ctrl+h":
            self.guess.backspace_letter()

    def check_input(self) -> bool | None:
        current = self.guess.current_guess
        current_word = "".join(self.guess.current_word).lower()
        if "" in self.guess.current_word:
            self.message.content = "Not enough letters"
            return
        if current_word not in Ta and current_word not in La:
            self.message.content = "Not in word list"
            return
        self.result = self.guess.check_solution(self.solution)
        for l in current:
            button = self.buttons[l.name]
            button.status = max(button.status or 0, l.status)
##        self.save_statistics()
        if self.result is not None:
            self.show_result()

    def copy_result(self) -> None:
        guesses = self.guess.valid_guesses
        trials = len(guesses) if self.result else "x"
        result = [f"Wordle {self.index} {trials}/6", ""]
        for row in guesses:
            result.append("".join(BLOCKS[l.status] for l in row))
        text = "\n".join(result)
        pyperclip.copy(text)
        old_content = self.message.content
        self.message.content = "Successfully copied to the clipboard."

        def restore():
            self.message.content = old_content

        self.message.set_timer(2, restore)

##    def save_statistics(self) -> None:
##        guesses = self.guess.valid_guesses
##        if self.result:
##            self.stats["stats"][len(guesses) - 1] += 1
##        is_streak = (
##            "last_played" in self.stats and self.index - self.stats["last_played"] == 1
##        )
##        current_streak = self.stats.get("current_streak", 0) if is_streak else 0
##        if self.result is not None:
##            self.stats["played"] += 1
##            current_streak += 1
##        max_streak = max(current_streak, self.stats.get("max_streak", 0))
##        data = {
##            "last_played": self.index,
##            "last_guesses": (
##                "".join("".join(str(l.name) for row in guesses for l in row)),
##                "".join("".join(str(l.status) for row in guesses for l in row)),
##            ),
##            "last_result": self.result,
##            "played": self.stats["played"] + 1,
##            "stats": self.stats["stats"],
##            "current_streak": current_streak,
##            "max_streak": max_streak,
##        }
##        self.stats.update(data)
##        self.stats_view.refresh()
##        with open(STATS_JSON, "w") as f:
##            json.dump(data, f, indent=2)

    def show_result(self) -> None:
        if self.result:
            content = "You Win!"
            self.header.stop_clock()
        else:
            content = f"Sorry, no more guesses.\nThe answer is:\n{self.solution}"
        self.message.content = content
##        self.message.show_eta(SEED_DATE + datetime.timedelta(days=self.index + 1))

    def handle_button_pressed(self, message: ButtonPressed) -> None:
        if self.result is not None:
            return
        self.message.content = ""
        if message.sender.name == "enter":
            self.check_input()
        elif message.sender.name == "backspace":
            self.guess.backspace_letter()
        else:
            self.guess.input_letter(message.sender.name)

    def get_index(self) -> int:
        # Pick a random index from the range of solutions.
        return random.randint(0,len(La)-1)
        #this_date = datetime.datetime.combine(datetime.date.today(), datetime.time())
        #return (this_date - SEED_DATE).days

    def init_game(self) -> None:
        if self.index > self.stats.get("last_played", -1):
            self.stats["last_result"] = None
            return
        slots = self.guess.slots
        for i, (letter, status) in enumerate(zip(*self.stats["last_guesses"])):
            slots[i].name = slots[i].label = letter
            slots[i].status = int(status)
            self.buttons[letter].status = max(
                self.buttons[letter].status or 0, int(status)
            )
        self.result = self.stats["last_result"]
        self.guess.current = i + 1
        if self.result is not None:
            self.show_result()

    async def on_mount(self) -> None:
        self.index = self.get_index()
        self.solution = La[self.index].upper()
##        self.log("Loading stats", STATS_JSON)
##        if not STATS_JSON.exists():
##            self.stats = INITIAL_STATS.copy()
##        else:
##            with open(STATS_JSON, "rb") as f:
##                self.stats = json.load(f)
        self.stats = INITIAL_STATS.copy()
        self.result: bool | None = None

        self.buttons = {
            name: Letter(name, True) for row in self.KEYBOARD for name in row
        }
        keyboard_rows = [
            KeyboardRow([self.buttons[k] for k in row]) for row in self.KEYBOARD
        ]
        # add enter and backspace buttons
        keyboard_rows[-1].children.insert(0, Button("ENTER", "enter", style=IDLE))
        keyboard_rows[-1].children.append(Button("⬅️", "backspace", style=IDLE))
        view = await self.push_view(DockView())
        self.header = CountdownHeader(TIME_LIMIT)
        self.message = GameMessage()
        await view.dock(self.header, edge="top")
        subview = DockView()
        self.guess = GuessView()
        self.init_game()
        await subview.dock(self.guess, size=26)
        await subview.dock(*keyboard_rows, size=4)
        right_side = DockView()
        self.stats_view = GameStats(self.stats)
        await right_side.dock(self.message, self.stats_view)
        await view.dock(right_side, edge="right", size=40)
        await view.dock(subview, edge="right")


def main():
    WordleApp.run(title="WORDATA", log="textual.log")


if __name__ == "__main__":
    main()
