"""Tests for the Selenium bridge (mocked Selenium + mocked Director)."""

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from thea.director.bridges.selenium import HumanElement, HumanDriver


def _mock_element(rect=None):
    el = MagicMock()
    el.rect = rect or {"x": 100, "y": 200, "width": 60, "height": 30}
    el.text = "Click me"
    el.is_displayed.return_value = True
    el.is_enabled.return_value = True
    el.get_attribute.return_value = "btn"
    return el


def _mock_director():
    d = MagicMock()
    d.mouse = MagicMock()
    d.keyboard = MagicMock()
    return d


class TestHumanElementCenter:
    def test_center_calculation(self):
        el = _mock_element({"x": 100, "y": 200, "width": 60, "height": 40})
        he = HumanElement(el, _mock_director())
        assert he._center() == (130, 220)

    def test_center_odd_size(self):
        el = _mock_element({"x": 0, "y": 0, "width": 51, "height": 31})
        he = HumanElement(el, _mock_director())
        assert he._center() == (25, 15)


class TestHumanElementClick:
    def test_click(self):
        director = _mock_director()
        he = HumanElement(_mock_element(), director)
        he.click()
        director.mouse.click.assert_called_once_with(130, 215)

    def test_double_click(self):
        director = _mock_director()
        he = HumanElement(_mock_element(), director)
        he.double_click()
        director.mouse.double_click.assert_called_once_with(130, 215)

    def test_right_click(self):
        director = _mock_director()
        he = HumanElement(_mock_element(), director)
        he.right_click()
        director.mouse.right_click.assert_called_once_with(130, 215)


class TestHumanElementType:
    @patch("thea.director.bridges.selenium.time.sleep")
    def test_type_clicks_first(self, mock_sleep):
        director = _mock_director()
        he = HumanElement(_mock_element(), director)
        he.type("hello")
        director.mouse.click.assert_called_once()
        director.keyboard.type.assert_called_once_with("hello", wpm=None)

    @patch("thea.director.bridges.selenium.time.sleep")
    def test_type_with_wpm(self, mock_sleep):
        director = _mock_director()
        he = HumanElement(_mock_element(), director)
        he.type("text", wpm=120)
        director.keyboard.type.assert_called_once_with("text", wpm=120)

    @patch("thea.director.bridges.selenium.time.sleep")
    def test_type_with_clear(self, mock_sleep):
        director = _mock_director()
        he = HumanElement(_mock_element(), director)
        he.type("new", clear=True)
        # Should press ctrl+a then Delete before typing.
        director.keyboard.press.assert_any_call("ctrl+a")
        director.keyboard.press.assert_any_call("Delete")
        director.keyboard.type.assert_called_once_with("new", wpm=None)


class TestHumanElementHover:
    def test_hover(self):
        director = _mock_director()
        el = _mock_element({"x": 50, "y": 100, "width": 80, "height": 40})
        he = HumanElement(el, director)
        he.hover()
        director.mouse.move_to.assert_called_once_with(90, 120, target_width=80.0)


class TestHumanElementPassthrough:
    def test_text(self):
        el = _mock_element()
        he = HumanElement(el, _mock_director())
        assert he.text == "Click me"

    def test_rect(self):
        el = _mock_element({"x": 10, "y": 20, "width": 30, "height": 40})
        he = HumanElement(el, _mock_director())
        assert he.rect == {"x": 10, "y": 20, "width": 30, "height": 40}

    def test_get_attribute(self):
        el = _mock_element()
        he = HumanElement(el, _mock_director())
        assert he.get_attribute("class") == "btn"

    def test_is_displayed(self):
        el = _mock_element()
        he = HumanElement(el, _mock_director())
        assert he.is_displayed() is True

    def test_is_enabled(self):
        el = _mock_element()
        he = HumanElement(el, _mock_director())
        assert he.is_enabled() is True

    def test_underlying_element(self):
        el = _mock_element()
        he = HumanElement(el, _mock_director())
        assert he.element is el


class TestHumanDriver:
    def test_get(self):
        driver = MagicMock()
        director = _mock_director()
        hd = HumanDriver(driver, director)
        hd.get("https://example.com")
        driver.get.assert_called_once_with("https://example.com")

    def test_find_element(self):
        driver = MagicMock()
        director = _mock_director()
        driver.find_element.return_value = _mock_element()
        hd = HumanDriver(driver, director)
        result = hd.find_element("id", "btn")
        assert isinstance(result, HumanElement)
        driver.find_element.assert_called_once_with("id", "btn")

    def test_find_elements(self):
        driver = MagicMock()
        director = _mock_director()
        driver.find_elements.return_value = [_mock_element(), _mock_element()]
        hd = HumanDriver(driver, director)
        results = hd.find_elements("css", ".item")
        assert len(results) == 2
        assert all(isinstance(r, HumanElement) for r in results)

    def test_title(self):
        driver = MagicMock()
        driver.title = "Test Page"
        hd = HumanDriver(driver, _mock_director())
        assert hd.title == "Test Page"

    def test_current_url(self):
        driver = MagicMock()
        driver.current_url = "https://example.com/page"
        hd = HumanDriver(driver, _mock_director())
        assert hd.current_url == "https://example.com/page"

    def test_quit(self):
        driver = MagicMock()
        hd = HumanDriver(driver, _mock_director())
        hd.quit()
        driver.quit.assert_called_once()

    def test_driver_property(self):
        driver = MagicMock()
        hd = HumanDriver(driver, _mock_director())
        assert hd.driver is driver

    def test_director_property(self):
        director = _mock_director()
        hd = HumanDriver(MagicMock(), director)
        assert hd.director is director
