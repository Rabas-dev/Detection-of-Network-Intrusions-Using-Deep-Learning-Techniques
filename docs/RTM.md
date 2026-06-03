# Requirements Traceability Matrix (RTM) — DeepNIDS

Maps every requirement to the design element that implements it and the
test(s) that verify it. Used as the bidirectional traceability evidence for the
Software Quality Engineering deliverable.

## Functional requirements

| ID | Requirement | Implemented in | Verified by (test) | Level |
| --- | --- | --- | --- | --- |
| FR-1 | Classify flows as Normal / DDoS / PortScan / BruteForce | `model.DNNClassifier`, `pipeline.analyze` | `test_classifier_emits_one_logit_per_class`, `test_classifier_predicts_each_profile_majority`, `test_classifier_output_contract` | Unit / Integration |
| FR-2 | Unsupervised anomaly detection via autoencoder | `model.Autoencoder`, `pipeline.analyze` | `test_autoencoder_reconstructs_input_shape`, `test_autoencoder_output_contract`, `test_attacks_have_higher_anomaly_score_than_normal` | Unit / Integration |
| FR-3 | Scale features to [0,1] before inference | `trainer.ModelHub.transform` | `test_transform_boundaries` (BVA) | Unit |
| FR-4 | Generate traffic matching attack profiles | `simulator.sample_features`, `NetworkSimulator` | `test_normal_traffic_has_no_failed_logins`, `test_bruteforce_is_defined_by_failed_logins`, `test_ddos_is_defined_by_high_connection_volume`, `test_portscan_is_defined_by_host_spreading`, `test_all_features_are_non_negative`, `test_build_dataset_is_balanced_and_shaped`, `test_simulator_mode_switch_changes_traffic` | Unit / Integration |
| FR-5 | Provide per-verdict feature attribution (XAI) | `pipeline._classifier_saliency` | `test_classifier_output_contract` (attribution length + normalisation) | Integration |
| FR-6 | Stream live classifications over WebSocket | `main.ws_traffic` | `test_traffic_stream_contract` | System |
| FR-7 | Stream live training metrics per epoch | `trainer.stream_train`, `main.ws_train` | `test_training_stream_emits_epochs_and_done` | System |
| FR-8 | Switch active attack profile via API | `simulator.set_mode`, `main.set_attack` | `test_attack_valid_mode`, `test_invalid_mode_raises` | System / Integration |
| FR-9 | Serve dashboard + report baseline metrics | `main.index`, `main.get_metrics` | `test_index_serves_dashboard`, `test_metrics_contract`, `test_model_eval_endpoint` | System |

## Non-functional requirements

| ID | Requirement (ISO/IEC 25010) | Implemented in | Verified by | Level |
| --- | --- | --- | --- | --- |
| NFR-1 | *Performance efficiency:* inference p95 latency < 5 ms | `pipeline.analyze` | `quality.benchmark` + latency quality gate | Performance |
| NFR-2 | *Functional suitability:* model macro-F1 ≥ 0.90 | `trainer.stream_train` | `quality.evaluate_model` + F1 quality gate | Model eval |
| NFR-3 | *Maintainability:* branch coverage ≥ 75 % | whole codebase | `pytest-cov` + CI `--cov-fail-under=75` | All |
| NFR-4 | *Reliability:* invalid input handled gracefully | `main.set_attack`, `simulator.set_mode`, `trainer.transform` | `test_attack_invalid_mode_is_rejected`, `test_invalid_mode_raises`, `test_transform_boundaries` | System / Unit |

## Coverage summary

- **9 / 9** functional requirements traced to ≥ 1 automated test.
- **4 / 4** non-functional requirements traced to a measurable quality gate.
- No orphan tests (every test maps back to a requirement above).
