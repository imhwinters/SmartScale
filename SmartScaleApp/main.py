import asyncio
import json
import sys
import threading
from bleak import BleakClient, BleakScanner
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DEVICE_NAME = "Scale"
CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
TOLERANCE = 3.0
HOLD_SECONDS = 2.0


class RecipeScale:
    def __init__(self, recipe):
        self.recipe = recipe
        self.steps = recipe["steps"]
        self.step_index = 0
        self.weight = 0.0
        self.baseline = 0.0
        self.held_since = None
        self.done = False
        self.advance_event = asyncio.Event()
        self.console = Console()

    def on_weight(self, sender, data):
        try:
            self.weight = float(data.decode().strip())
        except ValueError:
            pass

    def relative(self):
        return self.weight - self.baseline

    def step(self):
        return self.steps[self.step_index]

    def has_target(self):
        return "amount" in self.step()

    def on_target(self):
        if not self.has_target():
            return False
        return abs(self.relative() - self.step()["amount"]) <= TOLERANCE

    def tare(self):
        self.baseline = self.weight

    def advance(self):
        self.baseline = self.weight
        self.step_index += 1
        self.held_since = None
        if self.step_index >= len(self.steps):
            self.done = True

    def build_display(self, now):
        if self.done:
            return Panel(Text("✓  Recipe complete!", style="bold green"), border_style="green")

        step = self.step()
        grid = Table.grid(padding=(0, 1))
        grid.add_column()

        title = Text(self.recipe["name"], style="bold cyan")
        title.append(f"   —   Step {self.step_index + 1} of {len(self.steps)}", style="dim white")
        grid.add_row(title)
        grid.add_row(Text(""))
        grid.add_row(Text(step["instruction"], style="bold white"))
        grid.add_row(Text(""))

        if self.has_target():
            target = step["amount"]
            unit = step.get("unit", "g")
            rel = self.relative()
            on_target = self.on_target()

            weight_text = Text()
            weight_text.append(f"{rel:.1f}", style="bold green" if on_target else "bold yellow")
            weight_text.append(f" / {target} {unit}", style="dim")
            grid.add_row(weight_text)

            bar_width = 38
            clamped = max(0.0, min(rel, target))
            filled = int((clamped / target) * bar_width) if target > 0 else 0
            bar = Text("█" * filled + "░" * (bar_width - filled),
                       style="green" if on_target else "yellow")
            grid.add_row(bar)
            grid.add_row(Text(""))

            if on_target and self.held_since is not None:
                remaining = HOLD_SECONDS - (now - self.held_since)
                if remaining > 0:
                    grid.add_row(Text(f"✓  Hold steady — advancing in {remaining:.1f}s", style="bold green"))
                else:
                    grid.add_row(Text("✓  Advancing...", style="bold green"))
            elif on_target:
                grid.add_row(Text("✓  On target...", style="bold green"))
            elif rel < -TOLERANCE:
                grid.add_row(Text("Negative reading — press T + Enter to re-tare", style="dim red"))
            elif rel > target + TOLERANCE:
                grid.add_row(Text(f"Over by {rel - target:.1f} {unit} — remove some", style="dim red"))
            else:
                grid.add_row(Text(f"Add {target - rel:.1f} {unit} more", style="dim white"))
        else:
            grid.add_row(Text("Press Enter to continue", style="dim white"))

        grid.add_row(Text(""))
        grid.add_row(Text("T + Enter = tare   Q + Enter = quit", style="dim"))

        return Panel(grid, border_style="cyan")

    def _input_thread(self, loop):
        while not self.done:
            try:
                line = sys.stdin.readline().strip().lower()
                if line == "q":
                    self.done = True
                elif line == "t":
                    self.tare()
                elif line == "" and not self.has_target():
                    asyncio.run_coroutine_threadsafe(self._trigger_advance(), loop)
            except Exception:
                break

    async def _trigger_advance(self):
        self.advance_event.set()

    async def run_with_client(self, client):
        loop = asyncio.get_event_loop()
        threading.Thread(target=self._input_thread, args=(loop,), daemon=True).start()

        await client.start_notify(CHAR_UUID, self.on_weight)

        with Live(console=self.console, refresh_per_second=10) as live:
            while not self.done:
                now = loop.time()

                if self.has_target():
                    if self.on_target():
                        if self.held_since is None:
                            self.held_since = now
                        elif now - self.held_since >= HOLD_SECONDS:
                            self.advance()
                    else:
                        self.held_since = None
                else:
                    if self.advance_event.is_set():
                        self.advance_event.clear()
                        self.advance()

                live.update(self.build_display(now))
                await asyncio.sleep(0.1)

        await client.stop_notify(CHAR_UUID)

    async def run(self):
        self.console.print("[cyan]Scanning for Scale...[/cyan]")
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)

        if device is None:
            self.console.print("[red]Could not find Scale. Is it powered on and not already connected?[/red]")
            return

        self.console.print(f"[green]Found {device.name}, connecting...[/green]")
        async with BleakClient(device) as client:
            self.console.print("[green]Connected.[/green]")
            await self.run_with_client(client)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scale_recipe.py <recipe.json>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        recipe = json.load(f)
    asyncio.run(RecipeScale(recipe).run())


if __name__ == "__main__":
    main()