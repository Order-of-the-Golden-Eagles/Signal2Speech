using System;
using System.Collections.Generic;

namespace Signal2Speech.Core
{
    /// <summary>
    /// Turns source-specific input into <see cref="SelectionEvent"/>s.
    /// The round ID is stamped when the input is captured, never when it arrives.
    /// </summary>
    public sealed class InputAdapter
    {
        private readonly SelectionHandler _handler;
        private readonly string _source;
        private readonly string _eventPrefix;
        private int _eventCounter;
        private string _armedRoundId;

        public InputAdapter(SelectionHandler handler, string source)
        {
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            if (!InputSources.IsKnown(source)) throw new ArgumentException("Unknown source: " + source, nameof(source));
            _source = source;
            _eventPrefix = source == InputSources.Keyboard ? "k"
                : source == InputSources.Simulated ? "s"
                : source == InputSources.Recorded ? "rec"
                : "e";
        }

        public string Source => _source;

        /// <summary>
        /// Keyboard, simulator: capture and arrival are the same instant, so use the open round.
        /// Returns the outcome, or RejectedNoOpenRound when nothing is on screen.
        /// </summary>
        public Outcome SelectNow(string targetId)
        {
            var round = _handler.Current;
            if (round == null) return Outcome.RejectedNoOpenRound;
            return _handler.Handle(Create(round.Id, targetId));
        }

        /// <summary>
        /// Live EEG: call when the stimulus sequence for the current round starts (flashing begins).
        /// The round ID captured here is what the later decoder callback carries. Unverified: see #23.
        /// </summary>
        public void ArmCapture()
        {
            _armedRoundId = _handler.Current?.Id;
        }

        /// <summary>Live EEG: call from the vendor class-selection callback (on the main thread).</summary>
        public Outcome SelectCaptured(string targetId)
        {
            var roundId = _armedRoundId;
            _armedRoundId = null; // one decoded class per armed sequence
            if (roundId == null) return Outcome.RejectedNoOpenRound;
            return _handler.Handle(Create(roundId, targetId));
        }

        public SelectionEvent Create(string roundId, string targetId)
        {
            _eventCounter++;
            return new SelectionEvent(_source, roundId, _eventPrefix + _eventCounter, targetId);
        }
    }

    /// <summary>
    /// Vendor decoded class index → app target ID. Default mapping is an assumption until #23
    /// records the real mapping from the installed scene.
    /// </summary>
    public sealed class EegClassMap
    {
        private readonly Dictionary<int, string> _map;

        public EegClassMap(IDictionary<int, string> map) { _map = new Dictionary<int, string>(map); }

        /// <summary>UNVERIFIED default: class 1 → target-1, class 2 → target-2.</summary>
        public static EegClassMap AssumedDefault() => new EegClassMap(new Dictionary<int, string>
        {
            { 1, TargetIds.Target1 },
            { 2, TargetIds.Target2 },
        });

        /// <summary>Returns null for unmapped classes; the handler then never sees them.</summary>
        public string TargetFor(int classIndex) => _map.TryGetValue(classIndex, out var t) ? t : null;
    }
}
