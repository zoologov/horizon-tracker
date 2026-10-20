// Fixture client: reproduces the hash routes of HTML Access 2312.1 (home -> launchitems ->
// desktop) and, where the adapter reads the page, the structure the real bundle
// app-htmlaccess.4eb7424a56fc03317f06.js renders. The fixture server behind /fixture/*
// plays the broker; the real client talks XML to /broker/xml, which the adapter never needs.
//
// What is reproduced from the bundle, because the adapter depends on it:
//  - A desktop tile is li#<id> (no title) > button#launch-<id>[title=<name>], which holds
//    the icons, the overflow button.overflow-button.app-item-action[aria-haspopup] and,
//    while it is open, the tile menu; then div.ellipsis > p.ui-desktop-name[title]. The
//    overflow button stops its click, so opening the menu never launches the desktop.
//  - The tile menu is share-contextmenu.content-menu > ul#context-menu-container >
//    web-contextmenu > li#menu-item-*-btn. Each item is toggled by the hidden attribute,
//    never disabled: "Log Off" shows only for a desktop that holds a session. The menu
//    closes on a click anywhere in the document; Escape does nothing to it.
//  - The Blast session appends div#wmksContainer<N> (display:none until connected) with
//    canvas#mainCanvas into #canvas-container; canvas#canvas beside the container stays
//    hidden whatever happens.
// What is the fixture's own: the menu asks the broker for the tile's session when it
// opens (the real client already holds it from the launch-items list).
(function () {
  "use strict";

  var app = document.getElementById("app");
  var routes = { "#/home": initHome, "#/launchitems": initLaunchItems, "#/desktop": initDesktop };
  var menu = { id: null, element: null };
  var wmksCount = 0;

  function byId(id) { return document.getElementById(id); }

  function element(tag, attributes, text) {
    var node = document.createElement(tag);
    Object.keys(attributes || {}).forEach(function (name) { node.setAttribute(name, attributes[name]); });
    if (text) { node.textContent = text; }
    return node;
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
  }

  function record(name) { return post("/fixture/event", { name: name }); }

  function behaviour() {
    return fetch("/fixture/behaviour").then(function (response) { return response.json(); });
  }

  function render() {
    var route = location.hash.split("?")[0];
    if (!routes[route]) { location.hash = "#/home"; return; }
    closeMenu();
    fetch(route.slice(2) + ".html")
      .then(function (response) { return response.text(); })
      .then(function (html) { app.innerHTML = html; routes[route](); });
  }

  // --- #/home -------------------------------------------------------------------------

  function initHome() {
    byId("okDialogBtn").addEventListener("click", function () { byId("errorDialog").hidden = true; });
    byId("loginButton").addEventListener("click", function () {
      post("/fixture/login", { username: byId("username").value, password: byId("password").value })
        .then(function (response) {
          if (response.ok) { location.hash = "#/launchitems"; } else { byId("errorDialog").hidden = false; }
        });
    });
  }

  // --- #/launchitems ------------------------------------------------------------------

  function launchItems() {
    return fetch("/fixture/launch-items").then(function (response) {
      if (response.status === 401) { location.hash = "#/home"; throw new Error("not logged in"); }
      return response.json();
    });
  }

  function launch(id) {
    sessionStorage.setItem("desktop", id);
    location.hash = "#/desktop";
  }

  function tile(item) {
    var li = element("li", { id: item.id, tabindex: "-1" });
    var launchButton = element("button", {
      id: "launch-" + item.id, title: item.name, tabindex: "0",
      "class": "ui-btn ui-btn-a ui-desktop-corner", "aria-label": "Launch"
    });
    var overflow = element("button", {
      "aria-haspopup": "true", "aria-expanded": "false",
      "class": "overflow-button app-item-action primary-text-color", "aria-label": "More options"
    });
    var nameBox = element("div", { "class": "ellipsis" });

    launchButton.appendChild(element("img", { "class": "ui-desktop-icon", alt: item.name + " icon" }));
    launchButton.appendChild(element("img", { "class": "ui-desktop-icon", alt: "desktop icon", hidden: "" }));
    launchButton.appendChild(overflow);
    launchButton.addEventListener("click", function () { launch(item.id); });
    overflow.addEventListener("click", function (event) {
      event.stopPropagation();
      event.preventDefault();
      toggleMenu(item.id, launchButton);
    });
    nameBox.appendChild(element("p", { "class": "ui-desktop-name", title: item.name }, item.name));
    li.appendChild(launchButton);
    li.appendChild(nameBox);
    return li;
  }

  function closeMenu() {
    if (menu.element !== null) { menu.element.remove(); }
    menu = { id: null, element: null };
  }

  function toggleMenu(id, host) {
    if (menu.id === id) { closeMenu(); return; }
    closeMenu();
    var opening = { id: id, element: null };
    menu = opening;
    launchItems().then(function (items) {
      if (menu !== opening) { return; }
      var item = items.filter(function (each) { return each.id === id; })[0];
      opening.element = contextMenu(id, Boolean(item) && item.session !== "none");
      host.appendChild(opening.element);
    }).catch(function () {});
  }

  function menuEntry(id, label, shown, action) {
    var li = element("li", { id: id });
    var button = element("button");
    li.hidden = !shown;
    button.appendChild(element("div", { "class": "menu-item-icon" }));
    button.appendChild(document.createTextNode(" " + label + " "));
    li.appendChild(button);
    li.addEventListener("click", function (event) {
      event.stopPropagation();
      event.preventDefault();
      closeMenu();
      action();
    });
    return li;
  }

  function contextMenu(id, hasSession) {
    var host = element("share-contextmenu", { "class": "content-menu" });
    var container = element("ul", { id: "context-menu-container", "class": "context-menu-container south" });
    var entries = element("web-contextmenu");
    function nothing() {}

    entries.appendChild(menuEntry("menu-item-launch-btn", "Connect", true, function () { launch(id); }));
    entries.appendChild(menuEntry("menu-item-logoff-btn", "Log Off", hasSession, function () {
      byId("logoffDialog").dataset.desktop = id;
      byId("logoffDialog").hidden = false;
    }));
    entries.appendChild(menuEntry("menu-item-reset-btn", "Reset", false, nothing));
    entries.appendChild(menuEntry("menu-item-restart-btn", "Restart", false, nothing));
    entries.appendChild(menuEntry("menu-item-close-btn", "Close", false, nothing));
    container.appendChild(entries);
    host.appendChild(container);
    return host;
  }

  function initLaunchItems() {
    var list = byId("desktop-list");
    var dialog = byId("logoffDialog");

    launchItems().then(function (items) {
      items.forEach(function (item) { list.appendChild(tile(item)); });
    }).catch(function () {});
    byId("cancelDialogBtn").addEventListener("click", function () { dialog.hidden = true; });
    byId("okDialogBtn").addEventListener("click", function () {
      dialog.hidden = true;
      post("/fixture/kill-session", { id: dialog.dataset.desktop });
    });
  }

  // --- #/desktop ----------------------------------------------------------------------

  function startWmks() {
    var container = element("div", { id: "wmksContainer" + wmksCount, "class": "wmks" });
    wmksCount += 1;
    container.style.position = "absolute";
    container.style.display = "none";
    container.appendChild(element("canvas", { id: "mainCanvas", tabindex: "1" }));
    byId("canvas-container").appendChild(container);
    return container;
  }

  function initDesktop() {
    var id = sessionStorage.getItem("desktop");
    var scheme = location.protocol === "https:" ? "wss://" : "ws://";
    var dialog = byId("dialog");
    var mode = "fullscreen";
    var answered = false;
    var wmks = null;

    function draw() {
      behaviour().then(function (portal) {
        if (!portal.draw_canvas || !answered || wmks === null) { return; }
        var canvas = wmks.querySelector("canvas");
        canvas.width = 1280;
        canvas.height = 720;
        wmks.style.display = "block";
      });
    }

    behaviour().then(function (portal) {
      window.blast = new WebSocket(scheme + location.host + portal.blast_path + id + "/");
      window.blast.addEventListener("open", function () { wmks = startWmks(); draw(); });
      window.blast.addEventListener("close", function () {
        if (wmks !== null) { wmks.remove(); wmks = null; }
      });
    });

    byId("dialogMessage").textContent = "Enter full screen mode?";
    dialog.hidden = false;
    byId("cancelDialogBtn").addEventListener("click", function () {
      dialog.hidden = true;
      if (mode === "fullscreen") { answered = true; record("fullscreen-cancelled").then(draw); }
    });
    byId("okDialogBtn").addEventListener("click", function () {
      dialog.hidden = true;
      if (mode === "fullscreen") { answered = true; record("fullscreen-accepted").then(draw); }
      else { post("/fixture/kill-session", { id: id }); }
    });
    byId("sidebar-toggler").addEventListener("click", function () { byId("sidebar").hidden = !byId("sidebar").hidden; });
    byId("sidebar-logout-button").addEventListener("click", function () {
      mode = "logoff";
      byId("dialogMessage").textContent = "Log Off Desktop";
      dialog.hidden = false;
    });
  }

  // The bundle's share-contextmenu listens on the document: a click whose target is not
  // the overflow trigger closes the open menu. The overflow button stops its own click.
  document.addEventListener("click", function (event) {
    var target = event.target;
    if (target && target.getAttribute && target.getAttribute("data-id") === "overflow-button") { return; }
    closeMenu();
  });
  window.addEventListener("hashchange", render);
  render();
}());
