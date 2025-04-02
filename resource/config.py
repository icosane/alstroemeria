from enum import Enum

from PyQt6.QtCore import QLocale
from faster_whisper import available_models
from qfluentwidgets import (qconfig, QConfig, OptionsConfigItem, Theme,
                            OptionsValidator, EnumSerializer, ConfigSerializer)

class Language(Enum):
    """ Language enumeration """

    ENGLISH = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    RUSSIAN = QLocale(QLocale.Language.Russian, QLocale.Country.Russia)
    AUTO = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)

class LanguageSerializer(ConfigSerializer):
    """ Language serializer """

    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


models = available_models()

filtered_models = [m for m in models if not m.startswith('distil') and m != 'turbo']

Model = Enum('Model', {**{"NONE": "None"}, **{m.upper(): m for m in filtered_models}})

class ModelSerializer(ConfigSerializer):
    """ Model serializer """

    def __init__(self):
        self.model_map = {model.value: model for model in Model}

    def serialize(self, model):
        return model.value if model != Model.NONE else "None"

    def deserialize(self, value: str):
        if value == "None":
            return Model.NONE
        model = self.model_map.get(value)
        if model is None:
            raise ValueError(f"Invalid model: {value}")
        return model

class Device(Enum):
    CPU = "cpu"
    CUDA = "cuda"

class DeviceSerializer(ConfigSerializer):
    """ Device serializer """

    def __init__(self):
        self.device_map = {device.value: device for device in Device}

    def serialize(self, device):
        return device.value

    def deserialize(self, value: str):
        device = self.device_map.get(value)
        if device is None:
            raise ValueError(f"Invalid device: {value}")
        return device

class Config(QConfig):
    language = OptionsConfigItem(
        "MainWindow", "language", QLocale.Language.English, OptionsValidator(Language), LanguageSerializer(), restart=True)
    themeMode = OptionsConfigItem("Window", "themeMode", Theme.AUTO,
                                OptionsValidator(Theme), EnumSerializer(Theme), restart=True)
    model = OptionsConfigItem(
        "MainWindow", "model", Model.NONE, OptionsValidator(Model), ModelSerializer(), restart=False)
    device = OptionsConfigItem(
        "MainWindow", "device", Device.CPU, OptionsValidator(Device), DeviceSerializer(), restart=False)
    dpiScale = OptionsConfigItem(
        "MainWindow", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)   


cfg = Config()
qconfig.load('config/config.json', cfg)
