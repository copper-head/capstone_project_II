// Cal-AI Memory Page JavaScript
// Fetches /api/memories, groups by category, renders terminal-style accordions.
// Vanilla JS only — no framework dependencies.

(function () {
  "use strict";

  var container = document.getElementById("memory-container");
  var emptyState = document.getElementById("memory-empty");

  // Category display order (known categories first, then alphabetical).
  var CATEGORY_ORDER = [
    "preferences",
    "people",
    "vocabulary",
    "patterns",
    "corrections",
  ];

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function confidenceBadge(confidence) {
    var level = (confidence || "medium").toLowerCase();
    return (
      '<span class="badge-confidence badge-confidence--' +
      escapeHtml(level) +
      '">' +
      escapeHtml(level) +
      "</span>"
    );
  }

  function renderCategory(category, entries) {
    var count = entries.length;
    var countLabel = count === 1 ? "1 entry" : count + " entries";

    var entriesHtml = entries
      .map(function (entry) {
        return (
          '<div class="memory-entry">' +
          '<span class="memory-entry__key">' +
          escapeHtml(entry.key) +
          "</span>" +
          '<span class="memory-entry__value">' +
          escapeHtml(entry.value) +
          "</span>" +
          '<span class="memory-entry__confidence">' +
          confidenceBadge(entry.confidence) +
          "</span>" +
          "</div>"
        );
      })
      .join("");

    var section = document.createElement("div");
    section.className = "memory-category memory-category--expanded";
    section.innerHTML =
      '<div class="memory-category__header">' +
      '<span class="memory-category__title">' +
      escapeHtml(category) +
      "</span>" +
      '<span class="memory-category__count">' +
      escapeHtml(countLabel) +
      "</span>" +
      '<span class="memory-category__toggle">&#9654;</span>' +
      "</div>" +
      '<div class="memory-category__body">' +
      entriesHtml +
      "</div>";

    // Toggle accordion on header click.
    var header = section.querySelector(".memory-category__header");
    header.addEventListener("click", function () {
      section.classList.toggle("memory-category--expanded");
    });

    return section;
  }

  function groupByCategory(memories) {
    var groups = {};
    memories.forEach(function (m) {
      var cat = m.category || "other";
      if (!groups[cat]) {
        groups[cat] = [];
      }
      groups[cat].push(m);
    });
    return groups;
  }

  function sortCategories(groups) {
    var keys = Object.keys(groups);
    keys.sort(function (a, b) {
      var ia = CATEGORY_ORDER.indexOf(a);
      var ib = CATEGORY_ORDER.indexOf(b);
      // Known categories first, in order; unknown categories alphabetical.
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    });
    return keys;
  }

  function renderMemories(memories) {
    container.innerHTML = "";

    if (!memories || memories.length === 0) {
      container.hidden = true;
      emptyState.hidden = false;
      return;
    }

    emptyState.hidden = true;
    container.hidden = false;

    var groups = groupByCategory(memories);
    var orderedKeys = sortCategories(groups);

    orderedKeys.forEach(function (category) {
      var section = renderCategory(category, groups[category]);
      container.appendChild(section);
    });
  }

  function fetchMemories() {
    fetch("/api/memories")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        renderMemories(data);
      })
      .catch(function (err) {
        container.innerHTML =
          '<p class="memory-empty__text">Failed to load memories: ' +
          escapeHtml(err.message) +
          "</p>";
        container.hidden = false;
        emptyState.hidden = true;
      });
  }

  // Fetch fresh data on page load.
  fetchMemories();
})();
