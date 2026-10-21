"""Built-in sample texts; never loaded from user files."""

DEMO_LEFT = '// 一维 CA-CFAR 配置\nconst int TRAINING_CELLS = 4;\nconst int GUARD_CELLS = 1;\nconst int MAX_SAMPLES = 512;\n\nvoid detect(const uint32_t* power) {\n    const float scale = 1.20f;\n    for (int i = 0; i < MAX_SAMPLES; ++i) {\n        if (power[i] > threshold[i]) {\n            report_target(i);\n        }\n    }\n}\n'

DEMO_RIGHT = '// 一维 CA-CFAR 配置\nconst int TRAINING_CELLS = 4;\nconst int GUARD_CELLS = 2;\nconst int MAX_SAMPLES = 1024;\n\nvoid detect(const uint32_t* power) {\n    const float scale = 1.37f;\n    for (int i = 0; i < MAX_SAMPLES; ++i) {\n        if (!valid[i]) continue;\n        if (power[i] > threshold[i]) {\n            report_target(i);\n            record_power(power[i]);\n        }\n    }\n}\n'
