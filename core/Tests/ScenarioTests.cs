// Runs contracts/selection-scenarios.json against SelectionHandler.
// Shared by Unity EditMode (NUnit + com.unity.nuget.newtonsoft-json) and `dotnet test` (core/DotNetTests).
using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using Signal2Speech.Core;

namespace Signal2Speech.Core.Tests
{
    public class ScenarioTests
    {
        private sealed class RecordingSink : IActionSink
        {
            public readonly List<ConfirmedAction> Actions = new List<ConfirmedAction>();
            public void Execute(ConfirmedAction action) => Actions.Add(action);
        }

        internal static string ContractsDir()
        {
            foreach (var start in new[] { Directory.GetCurrentDirectory(), AppContext.BaseDirectory })
            {
                var dir = new DirectoryInfo(start);
                while (dir != null)
                {
                    var candidate = Path.Combine(dir.FullName, "contracts", "selection-scenarios.json");
                    if (File.Exists(candidate)) return Path.Combine(dir.FullName, "contracts");
                    dir = dir.Parent;
                }
            }
            throw new FileNotFoundException("contracts/selection-scenarios.json not found above " + Directory.GetCurrentDirectory());
        }

        internal static List<Choice> DemoChoices()
        {
            var root = JObject.Parse(File.ReadAllText(Path.Combine(ContractsDir(), "demo-round.json")));
            var list = new List<Choice>();
            foreach (var c in root["choices"])
                list.Add(new Choice((string)c["targetId"], (string)c["actionId"], (string)c["label"], (string)c["spokenText"]));
            return list;
        }

        private static IEnumerable<TestCaseData> Scenarios()
        {
            var root = JObject.Parse(File.ReadAllText(Path.Combine(ContractsDir(), "selection-scenarios.json")));
            foreach (var s in root["scenarios"])
                yield return new TestCaseData(s).SetName((string)s["name"]);
        }

        [TestCaseSource(nameof(Scenarios))]
        public void Scenario(JToken scenario)
        {
            var sink = new RecordingSink();
            var handler = new SelectionHandler(sink);
            var choices = DemoChoices();
            var i = 0;
            foreach (var step in scenario["steps"])
            {
                i++;
                var where = $"step {i} ({step["do"]})";
                switch ((string)step["do"])
                {
                    case "begin": handler.BeginChoiceRound(choices); break;
                    case "cancel": handler.Cancel(); break;
                    case "disconnect": handler.Disconnect(); break;
                    case "armLiveConfirm": handler.LiveEegConfirmArmed = true; break;
                    case "event":
                        var e = step["event"].ToObject<SelectionEvent>();
                        var outcome = handler.Handle(e);
                        Assert.AreEqual((string)step["expect"], outcome.ToString(), where);
                        break;
                    default: Assert.Fail("Unknown step " + step["do"]); break;
                }
                if (step["effects"] != null) Assert.AreEqual((int)step["effects"], sink.Actions.Count, where + " effects");
                if (step["action"] != null) Assert.AreEqual((string)step["action"], sink.Actions[sink.Actions.Count - 1].ActionId, where + " action");
                if (step["round"] != null)
                    Assert.AreEqual(step["round"].Type == JTokenType.Null ? null : (string)step["round"], handler.Current?.Id, where + " round");
            }
        }

        [Test]
        public void SampleEventsMatchContract()
        {
            var dir = Path.Combine(ContractsDir(), "events");
            var sink = new RecordingSink();
            var handler = new SelectionHandler(sink);
            handler.BeginChoiceRound(DemoChoices());
            SelectionEvent Load(string f) => JObject.Parse(File.ReadAllText(Path.Combine(dir, f))).ToObject<SelectionEvent>();

            Assert.AreEqual(Outcome.Previewed, handler.Handle(Load("preview.json")));
            Assert.AreEqual(Outcome.RejectedStaleRound, handler.Handle(Load("stale.json")));
            Assert.AreEqual(0, sink.Actions.Count);
            Assert.AreEqual(Outcome.Confirmed, handler.Handle(Load("confirm-fresh.json")));
            Assert.AreEqual(1, sink.Actions.Count);
            Assert.AreEqual("Washtenaw's AQI rose 186 points. Wayne's rose 168 points.", sink.Actions[0].SpokenText);
        }

        [Test]
        public void AdapterStampsRoundAtCaptureNotArrival()
        {
            var sink = new RecordingSink();
            var handler = new SelectionHandler(sink) { LiveEegConfirmArmed = true };
            var eeg = new InputAdapter(handler, InputSources.LiveEeg);
            var map = EegClassMap.AssumedDefault();

            handler.BeginChoiceRound(DemoChoices());
            eeg.ArmCapture();                                   // flashing starts in r1
            Assert.AreEqual(Outcome.Previewed, eeg.SelectCaptured(map.TargetFor(2)));
            // A second callback from the same r1 sequence arrives after r2 opened.
            Assert.AreEqual(Outcome.RejectedNoOpenRound, eeg.SelectCaptured(map.TargetFor(1)));
            eeg.ArmCapture();                                   // flashing starts in r2
            Assert.AreEqual(Outcome.Confirmed, eeg.SelectCaptured(map.TargetFor(1)));
            Assert.AreEqual(1, sink.Actions.Count);
            Assert.IsNull(map.TargetFor(7));
        }

        [Test]
        public void KeyboardAdapterUsesOpenRound()
        {
            var sink = new RecordingSink();
            var handler = new SelectionHandler(sink);
            var kb = new InputAdapter(handler, InputSources.Keyboard);
            Assert.AreEqual(Outcome.RejectedNoOpenRound, kb.SelectNow(TargetIds.Target1));
            handler.BeginChoiceRound(DemoChoices());
            Assert.AreEqual(Outcome.Previewed, kb.SelectNow(TargetIds.Target1));
            Assert.AreEqual(Outcome.Confirmed, kb.SelectNow(TargetIds.Target1));
            Assert.AreEqual(ActionIds.ShowSatellite, sink.Actions[0].ActionId);
        }
    }
}
