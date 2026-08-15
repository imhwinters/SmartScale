import asyncio
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

from bleak import BleakClient, BleakScanner


DEVICE_NAME = "Scale"
CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

TOLERANCE = 3.0
HOLD_SECONDS = 2.0


class ScaleBLE:
    """Runs Bleak in a dedicated asyncio thread."""

    def __init__(self, on_weight, on_status):
        self.on_weight = on_weight
        self.on_status = on_status

        self.loop = None
        self.client = None
        self.thread = None

        self.running = False

    def start(self):
        self.thread = threading.Thread(
            target=self._thread_main,
            daemon=True
        )
        self.thread.start()

    def _thread_main(self):
        asyncio.run(self._run())

    async def _run(self):
        self.loop = asyncio.get_running_loop()
        self.running = True

        try:
            self.on_status("Scanning for Scale...")

            device = await BleakScanner.find_device_by_name(
                DEVICE_NAME,
                timeout=15.0
            )

            if device is None:
                self.on_status("Scale not found")
                self.running = False
                return

            self.on_status(f"Connecting to {device.name}...")

            async with BleakClient(device) as client:
                self.client = client

                self.on_status("Connected")

                await client.start_notify(
                    CHAR_UUID,
                    self._notification
                )

                # Keep the BLE connection alive.
                while client.is_connected:
                    await asyncio.sleep(0.5)

                self.on_status("Scale disconnected")

        except Exception as e:
            self.on_status(f"BLE error: {e}")

        finally:
            self.running = False
            self.client = None

    def _notification(self, sender, data):
        try:
            weight = float(data.decode().strip())
            self.on_weight(weight)
        except (ValueError, UnicodeDecodeError):
            pass

    def stop(self):
        if self.loop and self.client:
            future = asyncio.run_coroutine_threadsafe(
                self._disconnect(),
                self.loop
            )

            try:
                future.result(timeout=3)
            except Exception:
                pass

    async def _disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()


class RecipeApp:
    def __init__(self, root, recipe):
        self.root = root
        self.recipe = recipe
        self.steps = recipe["steps"]

        self.step_index = 0

        # Raw reading from the scale.
        self.weight = 0.0

        # Weight at the beginning of the current step.
        self.baseline = 0.0

        # Used for the "hold steady" timer.
        self.held_since = None

        self.done = False

        # Communication from BLE thread -> GUI thread.
        self.ble_queue = queue.Queue()

        self.ble = ScaleBLE(
            self.queue_weight,
            self.queue_status
        )

        self.build_gui()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

        self.process_ble_queue()

        # Start BLE automatically.
        self.ble.start()

    # ---------------------------------------------------------
    # GUI
    # ---------------------------------------------------------

    def build_gui(self):
        self.root.title(self.recipe["name"])
        self.root.geometry("900x650")
        self.root.minsize(700, 500)

        self.root.configure(bg="#202124")

        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "TButton",
            font=("Arial", 13),
            padding=10
        )

        style.configure(
            "Big.TButton",
            font=("Arial", 16, "bold"),
            padding=15
        )

        style.configure(
            "TProgressbar",
            thickness=25
        )

        # -----------------------------------------------------
        # Header
        # -----------------------------------------------------

        header = tk.Frame(
            self.root,
            bg="#202124"
        )
        header.pack(
            fill="x",
            padx=30,
            pady=(25, 10)
        )

        self.recipe_label = tk.Label(
            header,
            text=self.recipe["name"],
            font=("Arial", 24, "bold"),
            fg="white",
            bg="#202124"
        )
        self.recipe_label.pack(side="left")

        self.connection_label = tk.Label(
            header,
            text="● Connecting...",
            font=("Arial", 12),
            fg="#fbbc04",
            bg="#202124"
        )
        self.connection_label.pack(
            side="right",
            pady=8
        )

        # -----------------------------------------------------
        # Step counter
        # -----------------------------------------------------

        self.step_counter = tk.Label(
            self.root,
            text="",
            font=("Arial", 14),
            fg="#aaaaaa",
            bg="#202124"
        )
        self.step_counter.pack(pady=(15, 5))

        # -----------------------------------------------------
        # Main card
        # -----------------------------------------------------

        self.card = tk.Frame(
            self.root,
            bg="#292a2d",
            padx=40,
            pady=35
        )
        self.card.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=10
        )

        self.instruction_label = tk.Label(
            self.card,
            text="",
            font=("Arial", 22, "bold"),
            fg="white",
            bg="#292a2d",
            wraplength=750,
            justify="center"
        )
        self.instruction_label.pack(
            pady=(10, 25)
        )

        # -----------------------------------------------------
        # Weight display
        # -----------------------------------------------------

        self.weight_label = tk.Label(
            self.card,
            text="",
            font=("Arial", 42, "bold"),
            fg="#fbbc04",
            bg="#292a2d"
        )
        self.weight_label.pack()

        self.target_label = tk.Label(
            self.card,
            text="",
            font=("Arial", 18),
            fg="#aaaaaa",
            bg="#292a2d"
        )
        self.target_label.pack(
            pady=(0, 15)
        )

        self.progress = ttk.Progressbar(
            self.card,
            orient="horizontal",
            mode="determinate",
            maximum=100
        )
        self.progress.pack(
            fill="x",
            padx=80,
            pady=10
        )

        self.status_label = tk.Label(
            self.card,
            text="",
            font=("Arial", 15),
            fg="#dddddd",
            bg="#292a2d",
            wraplength=700
        )
        self.status_label.pack(
            pady=15
        )

        # -----------------------------------------------------
        # Buttons
        # -----------------------------------------------------

        controls = tk.Frame(
            self.root,
            bg="#202124"
        )
        controls.pack(
            fill="x",
            padx=30,
            pady=(5, 25)
        )

        self.back_button = ttk.Button(
            controls,
            text="← Back",
            command=self.previous_step
        )
        self.back_button.pack(
            side="left"
        )

        self.tare_button = ttk.Button(
            controls,
            text="Tare Scale",
            command=self.tare
        )
        self.tare_button.pack(
            side="left",
            padx=10
        )

        self.skip_button = ttk.Button(
            controls,
            text="Skip Step",
            command=self.skip_step
        )
        self.skip_button.pack(
            side="left"
        )

        self.continue_button = ttk.Button(
            controls,
            text="Continue →",
            style="Big.TButton",
            command=self.continue_step
        )
        self.continue_button.pack(
            side="right"
        )

        self.update_display()

    # ---------------------------------------------------------
    # BLE communication
    # ---------------------------------------------------------

    def queue_weight(self, weight):
        self.ble_queue.put(("weight", weight))

    def queue_status(self, status):
        self.ble_queue.put(("status", status))

    def process_ble_queue(self):
        try:
            while True:
                event, value = self.ble_queue.get_nowait()

                if event == "weight":
                    self.weight = value

                elif event == "status":
                    self.update_connection_status(value)

        except queue.Empty:
            pass

        if not self.done:
            self.update_display()

        self.root.after(20, self.process_ble_queue)

    def update_connection_status(self, status):
        if status == "Connected":
            self.connection_label.config(
                text="● Scale connected",
                fg="#34a853"
            )

        elif "Scanning" in status:
            self.connection_label.config(
                text="● Scanning...",
                fg="#fbbc04"
            )

        elif "Connecting" in status:
            self.connection_label.config(
                text="● Connecting...",
                fg="#fbbc04"
            )

        elif "disconnected" in status.lower():
            self.connection_label.config(
                text="● Scale disconnected",
                fg="#ea4335"
            )

        else:
            self.connection_label.config(
                text=f"● {status}",
                fg="#ea4335"
            )

    # ---------------------------------------------------------
    # Recipe state
    # ---------------------------------------------------------

    def current_step(self):
        if self.done:
            return None

        return self.steps[self.step_index]

    def has_target(self):
        step = self.current_step()

        if step is None:
            return False

        return "amount" in step

    def relative_weight(self):
        return self.weight - self.baseline

    def on_target(self):
        if not self.has_target():
            return False

        target = self.current_step()["amount"]

        return abs(
            self.relative_weight() - target
        ) <= TOLERANCE

    # ---------------------------------------------------------
    # Display
    # ---------------------------------------------------------

    def update_display(self):
        if self.done:
            self.show_complete()
            return

        step = self.current_step()

        self.step_counter.config(
            text=f"Step {self.step_index + 1} of {len(self.steps)}"
        )

        self.instruction_label.config(
            text=step["instruction"]
        )

        if self.has_target():
            self.display_weighing_step()
        else:
            self.display_non_weighing_step()

    def display_weighing_step(self):
        step = self.current_step()

        target = step["amount"]
        unit = step.get("unit", "g")

        relative = self.relative_weight()
        on_target = self.on_target()

        self.weight_label.config(
            text=f"{relative:.1f} {unit}",
            fg="#34a853" if on_target else "#fbbc04"
        )

        self.target_label.config(
            text=f"Target: {target} {unit}"
        )

        # Progress bar.
        if target > 0:
            percentage = max(
                0,
                min(
                    100,
                    relative / target * 100
                )
            )
        else:
            percentage = 100

        self.progress["value"] = percentage

        # Automatically advance after holding the target.
        if on_target:
            now = self.root.after

            if self.held_since is None:
                self.held_since = self.monotonic_time()

            elapsed = (
                self.monotonic_time()
                - self.held_since
            )

            if elapsed >= HOLD_SECONDS:
                self.advance_step()
                return

            remaining = HOLD_SECONDS - elapsed

            self.status_label.config(
                text=f"✓ On target — hold steady "
                     f"for {remaining:.1f}s",
                fg="#34a853"
            )

        else:
            self.held_since = None

            if relative < -TOLERANCE:
                self.status_label.config(
                    text="Reading is below zero. "
                         "Tare the scale.",
                    fg="#ea4335"
                )

            elif relative > target + TOLERANCE:
                self.status_label.config(
                    text=f"Over by "
                         f"{relative - target:.1f} {unit} — "
                         f"remove some.",
                    fg="#ea4335"
                )

            else:
                self.status_label.config(
                    text=f"Add "
                         f"{target - relative:.1f} {unit} more.",
                    fg="#dddddd"
                )

        self.continue_button.config(
            text="Skip Step →"
        )

    def display_non_weighing_step(self):
        self.weight_label.config(
            text=""
        )

        self.target_label.config(
            text=""
        )

        self.progress["value"] = 0

        self.status_label.config(
            text="Press Continue when you're ready.",
            fg="#dddddd"
        )

        self.continue_button.config(
            text="Continue →"
        )

        self.held_since = None

    def show_complete(self):
        self.step_counter.config(
            text="All steps complete"
        )

        self.instruction_label.config(
            text="✓ Recipe complete!",
            fg="#34a853"
        )

        self.weight_label.config(
            text=""
        )

        self.target_label.config(
            text=""
        )

        self.progress["value"] = 100

        self.status_label.config(
            text="Enjoy!",
            fg="#34a853"
        )

        self.continue_button.config(
            text="Done",
            state="disabled"
        )

        self.skip_button.config(
            state="disabled"
        )

        self.back_button.config(
            state="normal"
        )

        self.done = True

    # ---------------------------------------------------------
    # Step controls
    # ---------------------------------------------------------

    def advance_step(self):
        self.step_index += 1
        self.baseline = self.weight
        self.held_since = None

        if self.step_index >= len(self.steps):
            self.done = True

        self.update_display()

    def continue_step(self):
        if self.done:
            return

        # Non-weighing steps simply advance.
        if not self.has_target():
            self.advance_step()

        # Weighing steps can also be manually skipped.
        else:
            self.advance_step()

    def skip_step(self):
        if self.done:
            return

        self.advance_step()

    def previous_step(self):
        if self.step_index <= 0:
            return

        self.step_index -= 1
        self.baseline = self.weight
        self.held_since = None
        self.done = False

        self.continue_button.config(
            state="normal"
        )

        self.skip_button.config(
            state="normal"
        )

        self.update_display()

    # ---------------------------------------------------------
    # Scale controls
    # ---------------------------------------------------------

    def tare(self):
        self.baseline = self.weight
        self.held_since = None

        self.status_label.config(
            text="✓ Scale tared",
            fg="#34a853"
        )

        self.update_display()

    # ---------------------------------------------------------
    # Timing
    # ---------------------------------------------------------

    def monotonic_time(self):
        import time
        return time.monotonic()

    # ---------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------

    def close(self):
        self.done = True

        try:
            self.ble.stop()
        except Exception:
            pass

        self.root.destroy()


def load_recipe():
    if len(sys.argv) >= 2:
        filename = sys.argv[1]
    else:
        temp_root = tk.Tk()
        temp_root.withdraw()

        filename = filedialog.askopenfilename(
            title="Open Recipe",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*")
            ]
        )

        temp_root.destroy()

        if not filename:
            return None

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        messagebox.showerror(
            "Recipe Error",
            f"Could not load recipe:\n\n{e}"
        )
        return None


def main():
    recipe = load_recipe()

    if recipe is None:
        return

    root = tk.Tk()

    RecipeApp(
        root,
        recipe
    )

    root.mainloop()


if __name__ == "__main__":
    main()
