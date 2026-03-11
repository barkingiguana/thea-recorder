"""Selenium WebDriver bridge for the Thea Director.

Combines Selenium's element-finding intelligence with the Director's
human-like physical interaction.  The result: Selenium locates elements
in the DOM, and the Director moves the mouse and types with realistic
motion and timing so the recording looks like a real user.

Usage::

    from selenium import webdriver
    from thea.director import Director
    from thea.director.bridges.selenium import HumanDriver

    director = Director(":99")
    driver = webdriver.Chrome(options=options)
    human = HumanDriver(driver, director)

    human.get("https://example.com")
    human.find_element(By.ID, "email").type("user@example.com")
    human.find_element(By.ID, "submit").click()

Requires the ``selenium`` package: ``pip install thea-recorder[selenium]``
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement

from ..director import Director


class HumanElement:
    """A Selenium WebElement wrapped with human-like interaction.

    Don't construct directly — use :meth:`HumanDriver.find_element`.
    """

    def __init__(self, element: WebElement, director: Director):
        self._element = element
        self._director = director

    @property
    def element(self) -> WebElement:
        """The underlying Selenium WebElement."""
        return self._element

    def _center(self) -> tuple[int, int]:
        """Get the center coordinates of this element on the display."""
        rect = self._element.rect
        return (
            int(rect["x"] + rect["width"] / 2),
            int(rect["y"] + rect["height"] / 2),
        )

    def _target_width(self) -> float:
        """Get the element's width (for Fitts's Law duration)."""
        return float(self._element.rect["width"])

    def click(self) -> None:
        """Move the mouse to this element and click with human-like motion."""
        x, y = self._center()
        self._director.mouse.click(x, y)

    def double_click(self) -> None:
        """Move to this element and double-click."""
        x, y = self._center()
        self._director.mouse.double_click(x, y)

    def right_click(self) -> None:
        """Move to this element and right-click."""
        x, y = self._center()
        self._director.mouse.right_click(x, y)

    def type(self, text: str, *, wpm: float | None = None, clear: bool = False) -> None:
        """Click this element to focus it, then type with human-like rhythm.

        Args:
            text: Text to type.
            wpm: Typing speed override.
            clear: If *True*, clear the field first (Ctrl+A, Delete).
        """
        self.click()
        time.sleep(0.1)
        if clear:
            self._director.keyboard.press("ctrl+a")
            time.sleep(0.05)
            self._director.keyboard.press("Delete")
            time.sleep(0.05)
        self._director.keyboard.type(text, wpm=wpm)

    def hover(self) -> None:
        """Move the mouse to this element without clicking."""
        x, y = self._center()
        self._director.mouse.move_to(x, y, target_width=self._target_width())

    # --- Pass-through to underlying element for non-interaction queries ---

    @property
    def text(self) -> str:
        return self._element.text

    @property
    def rect(self) -> dict:
        return self._element.rect

    def get_attribute(self, name: str) -> str | None:
        return self._element.get_attribute(name)

    def is_displayed(self) -> bool:
        return self._element.is_displayed()

    def is_enabled(self) -> bool:
        return self._element.is_enabled()


class HumanDriver:
    """A Selenium WebDriver wrapped with human-like interaction.

    Element-finding uses Selenium (DOM queries).  Physical interaction
    (click, type, hover) uses the Director (human-like mouse and keyboard).

    Args:
        driver: A Selenium WebDriver instance.
        director: A thea-director Director instance.
    """

    def __init__(self, driver: WebDriver, director: Director):
        self._driver = driver
        self._director = director

    @property
    def driver(self) -> WebDriver:
        """The underlying Selenium WebDriver."""
        return self._driver

    @property
    def director(self) -> Director:
        """The Director providing human-like interaction."""
        return self._director

    def get(self, url: str) -> None:
        """Navigate to a URL."""
        self._driver.get(url)

    def find_element(self, by: str, value: str) -> HumanElement:
        """Find an element using Selenium and wrap it for human-like interaction.

        Args:
            by: Selenium locator strategy (e.g. ``By.ID``, ``By.CSS_SELECTOR``).
            value: Locator value.
        """
        element = self._driver.find_element(by, value)
        return HumanElement(element, self._director)

    def find_elements(self, by: str, value: str) -> list[HumanElement]:
        """Find elements using Selenium and wrap them."""
        elements = self._driver.find_elements(by, value)
        return [HumanElement(e, self._director) for e in elements]

    @property
    def title(self) -> str:
        return self._driver.title

    @property
    def current_url(self) -> str:
        return self._driver.current_url

    def quit(self) -> None:
        """Quit the browser."""
        self._driver.quit()
