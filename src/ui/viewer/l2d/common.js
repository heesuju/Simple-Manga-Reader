// Shared helpers used by viewer_41.html (Spine 4.1 / pixi-spine),
// viewer_40.html (4.0 / spine-webgl), and viewer_38.html (3.8 / spine-webgl).
// Library-agnostic — operates only on the spine Skeleton/AnimationState API
// which is stable across all three runtimes. Exposes a global L2D object.
(function (global) {
  var L2D = {};

  // Pick a default animation: prefer shortest "idle"-containing name; ties
  // broken by natural (numerical) sort so "Idle_02" < "Idle_10".
  L2D.pickDefaultAnim = function (names) {
    if (!names || names.length === 0) return -1;

    var idle = names.filter(function (n) {
      return n.toLowerCase().includes('idle');
    });

    if (idle.length === 0) return 0;

    function extractNumber(str) {
      var match = str.match(/\d+/);
      return match ? parseInt(match[0], 10) : Infinity;
    }

    idle.sort(function (a, b) {
      // 1. Shortest length first
      if (a.length !== b.length) return a.length - b.length;

      // 2. Numeric comparison (if numbers exist)
      var numA = extractNumber(a);
      var numB = extractNumber(b);
      if (numA !== numB) return numA - numB;

      // 3. Final fallback: lexicographic
      return a.localeCompare(b);
    });

    return names.indexOf(idle[0]);
  };

  // Set of bones that drive visible geometry: each slot.bone with an
  // attachment, plus every bone weighted by a weighted-mesh attachment.
  // Bones outside this set are control/IK rigs — shaking them does nothing.
  L2D.computeMeshBones = function (skeleton) {
    var set = new Set();
    var bones = skeleton.bones;
    var slots = skeleton.slots;
    for (var si = 0; si < slots.length; si++) {
      var slot = slots[si];
      var att = slot.getAttachment ? slot.getAttachment() : slot.attachment;
      if (!att) continue;
      if (att.bones && att.bones.length) {
        // Weighted mesh: arr is [count, idx, idx, ..., count, idx, ...]
        var arr = att.bones;
        var i = 0;
        while (i < arr.length) {
          var count = arr[i++];
          for (var j = 0; j < count; j++) {
            var idx = arr[i++];
            if (idx >= 0 && idx < bones.length) set.add(bones[idx]);
          }
        }
      } else if (slot.bone) {
        set.add(slot.bone);
      }
    }
    return set;
  };

  // Detect bones whose descendants should not lean (head/face). Combines a
  // topological hub finder (most direct children below 30% depth) with a
  // name-based fallback (any bone whose name contains "head" or "face").
  // Caches results on the skeleton instance; safe to call repeatedly.
  L2D.computeHeadStructure = function (skeleton) {
    if (skeleton._headDescendants) return;

    var maxD = 1;
    skeleton.bones.forEach(function (b) {
      var d = 0, c = b;
      while (c.parent) { d++; c = c.parent; }
      b._hDepth = d;
      if (d > maxD) maxD = d;
    });
    skeleton._maxDepth = maxD;

    skeleton._descCounts = new Map();
    function countDesc(b) {
      var count = 0;
      for (var i = 0; i < b.children.length; i++) {
        count += 1 + countDesc(b.children[i]);
      }
      skeleton._descCounts.set(b, count);
      return count;
    }
    countDesc(skeleton.getRootBone());

    var maxChildren = -1;
    var hubBone = null;
    var minDepth = Math.max(1, Math.floor(skeleton._maxDepth * 0.3));
    skeleton.bones.forEach(function (b) {
      if (b._hDepth >= minDepth && b.children.length > maxChildren) {
        maxChildren = b.children.length;
        hubBone = b;
      }
    });

    var headDescendants = new Set();
    function markDescendants(b) {
      headDescendants.add(b);
      for (var c of b.children) markDescendants(c);
    }
    if (hubBone) {
      for (var c of hubBone.children) markDescendants(c);
    }
    skeleton.bones.forEach(function (b) {
      var name = b.data && b.data.name ? b.data.name.toLowerCase() : '';
      if (name.includes('head') || name.includes('face')) {
        for (var c of b.children) markDescendants(c);
      }
    });
    skeleton._headDescendants = headDescendants;
  };

  // Click-shake impulse: upward kick + sideways jiggle + small rotation
  // jitter. Lazily initializes the bone's entry in the boneShakes map.
  L2D.applyShake = function (bone, strength, boneShakes) {
    if (strength === undefined) strength = 1.0;
    if (!boneShakes.has(bone)) {
      boneShakes.set(bone, {
        baseRot: bone.rotation,
        baseX: bone.x,
        baseY: bone.y,
        rot: 0, vel: 0,
        x: 0, y: 0,
        vx: 0, vy: 0
      });
    }
    var s = boneShakes.get(bone);
    s.vy += -8 * strength;
    s.vx += (Math.random() - 0.5) * 6 * strength;
    s.vel += (Math.random() - 0.5) * 4 * strength;
  };

  global.L2D = L2D;
})(window);
