import 'dart:io';

import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import 'package:image_picker/image_picker.dart';

/// Takes the photo of a price tag. Null when the shopper backs out.
abstract class PhotoSource {
  Future<String?> take();
}

class CameraPhotoSource implements PhotoSource {
  const CameraPhotoSource();

  @override
  Future<String?> take() async {
    final photo = await ImagePicker().pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
      maxWidth: 2000,
    );
    return photo?.path;
  }
}

/// Reads the text of a photo. It runs on the phone: the image is not sent to anyone for
/// reading, only to our own server as the evidence the shopper chose to contribute.
abstract class TextReader {
  Future<String> read(String photoPath);
}

class MlKitTextReader implements TextReader {
  const MlKitTextReader();

  @override
  Future<String> read(String photoPath) async {
    final recognizer = TextRecognizer(script: TextRecognitionScript.latin);
    try {
      final result = await recognizer.processImage(
        InputImage.fromFile(File(photoPath)),
      );
      return result.text;
    } finally {
      await recognizer.close();
    }
  }
}
