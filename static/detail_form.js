// 詳細情報フォームのカテゴリ連動。追加フォームと編集フォームで共用。
(function () {
  var cfg = {
    "移動": {
      subLabel: "手段", subs: ["飛行機", "新幹線", "電車", "バス", "車", "船", "徒歩", "その他"],
      nameLabel: "便名・列車名など", namePh: "例：ANA471 / のぞみ123",
      from: true, to: true,
      timeFrom: true, timeFromLabel: "出発時刻",
      timeTo: true, timeToLabel: "到着時刻", urlLabel: "予約・リンク"
    },
    "宿泊": {
      subLabel: "タイプ", subs: ["ホテル", "旅館", "民宿", "ゲストハウス", "その他"],
      nameLabel: "宿名", namePh: "例：那覇ビーチホテル",
      from: false, to: false,
      timeFrom: true, timeFromLabel: "チェックイン",
      timeTo: true, timeToLabel: "チェックアウト", urlLabel: "予約・リンク"
    },
    "食事": {
      subLabel: "区分", subs: ["朝食", "昼食", "夕食", "カフェ", "その他"],
      nameLabel: "店名", namePh: "例：海ぶどう食堂",
      from: false, to: false,
      timeFrom: true, timeFromLabel: "時刻",
      timeTo: false, urlLabel: "リンク"
    },
    "その他": {
      subLabel: "", subs: [],
      nameLabel: "名称", namePh: "例：お土産購入",
      from: false, to: false,
      timeFrom: false, timeTo: false, urlLabel: "リンク"
    }
  };

  function init() {
    var cat = document.getElementById("catSelect");
    if (!cat) return;
    var els = {
      fldSubtype: document.getElementById("fld-subtype"),
      lblSubtype: document.getElementById("lbl-subtype"),
      subtype: document.getElementById("subtypeSelect"),
      lblName: document.getElementById("lbl-name"),
      name: document.getElementById("nameInput"),
      fldFrom: document.getElementById("fld-from"),
      fldTo: document.getElementById("fld-to"),
      fldTimeFrom: document.getElementById("fld-timefrom"),
      lblTimeFrom: document.getElementById("lbl-timefrom"),
      fldTimeTo: document.getElementById("fld-timeto"),
      lblTimeTo: document.getElementById("lbl-timeto"),
      lblUrl: document.getElementById("lbl-url")
    };
    var current = (els.subtype && els.subtype.dataset.current) || "";

    function show(el, on) { if (el) el.style.display = on ? "" : "none"; }

    function apply(firstRun) {
      var c = cfg[cat.value] || cfg["その他"];
      show(els.fldSubtype, c.subs.length > 0);
      els.lblSubtype.textContent = c.subLabel;
      els.subtype.innerHTML = "";
      c.subs.forEach(function (s) {
        var o = document.createElement("option");
        o.value = s; o.textContent = s; els.subtype.appendChild(o);
      });
      if (firstRun && current && c.subs.indexOf(current) !== -1) {
        els.subtype.value = current;
      }
      els.lblName.textContent = c.nameLabel;
      els.name.placeholder = c.namePh;
      show(els.fldFrom, c.from);
      show(els.fldTo, c.to);
      show(els.fldTimeFrom, c.timeFrom);
      if (c.timeFrom) els.lblTimeFrom.textContent = c.timeFromLabel;
      show(els.fldTimeTo, c.timeTo);
      if (c.timeTo) els.lblTimeTo.textContent = c.timeToLabel;
      els.lblUrl.textContent = c.urlLabel;
    }

    cat.addEventListener("change", function () { apply(false); });
    apply(true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
