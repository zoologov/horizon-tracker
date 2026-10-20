// Fixture client: reproduces the hash routes of HTML Access 2312 (home -> launchitems ->
// desktop) over the static fragments beside it. The fixture server behind /fixture/* plays
// the broker; the real client talks XML to /broker/xml, which the adapter never needs here.
(function () {
  "use strict";

  var app = document.getElementById("app");
  var routes = { "#/home": initHome, "#/launchitems": initLaunchItems, "#/desktop": initDesktop };

  function byId(id) { return document.getElementById(id); }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
  }

  function record(name) { return post("/fixture/event", { name: name }); }

  function render() {
    var route = location.hash.split("?")[0];
    if (!routes[route]) { location.hash = "#/home"; return; }
    fetch(route.slice(2) + ".html")
      .then(function (response) { return response.text(); })
      .then(function (html) { app.innerHTML = html; routes[route](); });
  }

  function initHome() {
    byId("okDialogBtn").addEventListener("click", function () { byId("errorDialog").hidden = true; });
    byId("loginButton").addEventListener("click", function () {
      post("/fixture/login", { username: byId("username").value, password: byId("password").value })
        .then(function (response) {
          if (response.ok) { location.hash = "#/launchitems"; } else { byId("errorDialog").hidden = false; }
        });
    });
  }

  function launchItems() {
    return fetch("/fixture/launch-items").then(function (response) {
      if (response.status === 401) { location.hash = "#/home"; throw new Error("not logged in"); }
      return response.json();
    });
  }

  function tileId(tile) { return tile.querySelector("[id^='launch-']").id.slice("launch-".length); }

  function launch(id) {
    sessionStorage.setItem("desktop", id);
    location.hash = "#/desktop";
  }

  function initLaunchItems() {
    var menu = byId("tile-menu");
    var menuTile = null;

    launchItems().catch(function () {});
    document.querySelectorAll("#launch-items .launch-item").forEach(function (tile) {
      tile.querySelector("[id^='launch-']").addEventListener("click", function () { launch(tileId(tile)); });
      tile.querySelector(".more-button").addEventListener("click", function () {
        launchItems().then(function (items) {
          var item = items.filter(function (each) { return each.id === tileId(tile); })[0];
          var noSession = !item || item.session === "none";
          byId("menu-item-logoff-btn").disabled = noSession;
          byId("menu-item-reset-btn").disabled = noSession;
          menuTile = tile;
          menu.hidden = false;
        });
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { menu.hidden = true; }
    });
    byId("menu-item-launch-btn").addEventListener("click", function () { launch(tileId(menuTile)); });
    byId("menu-item-logoff-btn").addEventListener("click", function () {
      menu.hidden = true;
      byId("logoffDialog").hidden = false;
    });
    byId("cancelDialogBtn").addEventListener("click", function () { byId("logoffDialog").hidden = true; });
    byId("okDialogBtn").addEventListener("click", function () {
      byId("logoffDialog").hidden = true;
      post("/fixture/kill-session", { id: tileId(menuTile) });
    });
  }

  function initDesktop() {
    var id = sessionStorage.getItem("desktop");
    var scheme = location.protocol === "https:" ? "wss://" : "ws://";
    var dialog = byId("dialog");
    var mode = "fullscreen";

    window.blast = new WebSocket(scheme + location.host + "/r/" + id + "/");

    function draw() {
      fetch("/fixture/behaviour")
        .then(function (response) { return response.json(); })
        .then(function (behaviour) {
          if (behaviour.draw_canvas) { byId("canvas").width = 1280; byId("canvas").height = 720; }
        });
    }

    byId("dialogMessage").textContent = "Enter full screen mode?";
    dialog.hidden = false;
    byId("cancelDialogBtn").addEventListener("click", function () {
      dialog.hidden = true;
      if (mode === "fullscreen") { record("fullscreen-cancelled").then(draw); }
    });
    byId("okDialogBtn").addEventListener("click", function () {
      dialog.hidden = true;
      if (mode === "fullscreen") { record("fullscreen-accepted").then(draw); }
      else { post("/fixture/kill-session", { id: id }); }
    });
    byId("sidebar-toggler").addEventListener("click", function () { byId("sidebar").hidden = !byId("sidebar").hidden; });
    byId("sidebar-logout-button").addEventListener("click", function () {
      mode = "logoff";
      byId("dialogMessage").textContent = "Log Off Desktop";
      dialog.hidden = false;
    });
  }

  window.addEventListener("hashchange", render);
  render();
}());
