

from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
import os
import cv2
import numpy as np
from io import BytesIO
import base64
from flask import jsonify

def pil_to_base64(img):
    buffer = BytesIO()
    img.save(buffer, format="JPEG")  # or PNG
    img_bytes = buffer.getvalue()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    return img_b64



def load_yolo_model():
    try:
        # Get the absolute path to the model file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, 'best.pt')
        
        print(f"Looking for YOLO model at: {model_path}")
        
        if os.path.exists(model_path):
            model = YOLO(model_path)
            print("YOLO model loaded successfully!")
        else:
            print(f"YOLO model file not found at: {model_path}")
            print(f"Files in directory: {os.listdir(script_dir)}")
            return None
    except Exception as e:
        print(f"Error loading YOLO model: {e}")
        return None
    return model
    
    





def predict_face_shape(image_path, model):
    
    try:
        # Use lower confidence threshold for better detection
        results = model(image_path, conf=0.1)  # Lowered from default 0.25
        
        print(f"Processing image: {image_path}")
        print(f"Number of results: {len(results)}")
        
        # Load original image
        image = cv2.imread(image_path)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        print(f"Image shape: {image.shape}")
        
        # Get prediction results
        for result in results:
            print(f"Number of boxes detected: {len(result.boxes)}")
            print(f"Available classes: {result.names}")
            
            if len(result.boxes) > 0:
                # Find the box with highest confidence
                best_box = None
                best_conf = 0.0
                best_cls_name = ""
                
                # First pass: find the highest confidence detection
                for box in result.boxes:
                    conf = float(box.conf)
                    cls_id = int(box.cls)
                    cls_name = result.names[cls_id]
                    
                    print(f"   Detection: {cls_name}: {conf:.1%}")
                    
                    if conf > best_conf:
                        best_conf = conf
                        best_box = box
                        best_cls_name = cls_name
                
                print(f"✅ BEST DETECTION: {best_cls_name} with {best_conf:.1%} confidence")
                
                # Draw ONLY the best detection (highest confidence)
                if best_box is not None:
                    # Get coordinates for the best detection
                    x1, y1, x2, y2 = best_box.xyxy[0].cpu().numpy()
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    
                    # Choose color based on the best class
                    colors = {
                        'oval': (0, 255, 0),      # Green
                        'ovale': (0, 255, 0),     # Green (alternative spelling)
                        'round': (255, 0, 0),     # Red  
                        'square': (0, 0, 255),    # Blue
                        'rectangular': (255, 255, 0)  # Yellow
                    }
                    color = colors.get(best_cls_name.lower(), (255, 255, 255))
                    
                    # Use thick line for the best (and only) detection
                    thickness = 6
                    
                    # Draw face shape outline
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    width = x2 - x1
                    height = y2 - y1
                    
                    # Draw different shapes based on the best prediction
                    if best_cls_name.lower() in ['oval', 'ovale']:
                        cv2.ellipse(image_rgb, (center_x, center_y), 
                                  (width//2, height//2), 0, 0, 360, color, thickness)
                        
                    elif best_cls_name.lower() == 'round':
                        radius = min(width, height) // 2
                        cv2.circle(image_rgb, (center_x, center_y), radius, color, thickness)
                        
                    elif best_cls_name.lower() == 'square':
                        side = min(width, height)
                        square_x1 = center_x - side//2
                        square_y1 = center_y - side//2
                        square_x2 = center_x + side//2
                        square_y2 = center_y + side//2
                        cv2.rectangle(image_rgb, (square_x1, square_y1), 
                                    (square_x2, square_y2), color, thickness)
                        
                    elif best_cls_name.lower() == 'rectangular':
                        cv2.rectangle(image_rgb, (x1, y1), (x2, y2), color, thickness)
                    
                    else:
                        cv2.rectangle(image_rgb, (x1, y1), (x2, y2), color, thickness)
                    
                    # Draw label for the best detection
                    label = f"{best_cls_name.upper()}: {best_conf:.1%}"
                    
                    # Draw label background
                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
                    cv2.rectangle(image_rgb, (x1, y1 - label_size[1] - 10), 
                                (x1 + label_size[0], y1), color, -1)
                    
                    # Draw label text
                    cv2.putText(image_rgb, label, (x1, y1 - 5), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

                # Convert the annotated image_rgb to PIL Image
                pil_image = Image.fromarray(image_rgb)
                b64_image = pil_to_base64(pil_image)

                # Return the BEST detection (highest confidence)
                return {
                    "success": True,
                    "message": "Face shape detected",
                    "face_shape": best_cls_name,      # Use best detection
                    "confidence": best_conf,          # Use best confidence
                    "image": f"data:image/jpeg;base64,{b64_image}"  # full base64 format
                }
            


            else:
                print("❌ No boxes detected - trying different approach")
                
                # Try with even lower confidence
                results_low = model(image_path, conf=0.05)
                
                for result_low in results_low:
                    if len(result_low.boxes) > 0:
                        print(f"✅ Found {len(result_low.boxes)} boxes with very low confidence")
                        # Process with the low confidence results
                        for box in result_low.boxes:
                            cls_id = int(box.cls)
                            conf = float(box.conf)
                            cls_name = result_low.names[cls_id]
                            print(f"   Very low conf detection: {cls_name}: {conf:.3f}")
                    else:
                        print("❌ Still no boxes detected even with very low confidence")
                
                return {
                    "success": False,
                    "message": "No face shape detected. Try a clearer image with better lighting.",
                    "debug_info": f"Image size: {image.shape}, Available classes: {list(result.names.values())}"
                }        
                
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
    
    


    