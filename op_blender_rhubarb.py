import bpy
from bpy.props import IntProperty, FloatProperty
import blf
import bgl
import io
import sys
import select
import subprocess
from threading  import Thread
from queue import Queue, Empty
import json
import os

class RhubarbLipsyncOperator(bpy.types.Operator):
    """Run Rhubarb lipsync"""
    bl_idname = "object.rhubarb_lipsync"
    bl_label = "Rhubarb lipsync"

    cue_prefix = 'Mouth_'
    hold_frame_threshold = 4

    @classmethod
    def poll(cls, context):
        return context.preferences.addons[__package__].preferences.executable_path and \
            context.selected_pose_bones and \
            context.object.pose_library.mouth_shapes.sound_file

    def modal(self, context, event):
        wm = context.window_manager
        wm.progress_update(50)

        try:
            (stdout, stderr) = self.rhubarb.communicate(timeout=1)
        
            try:
                result = json.loads(stderr)
                if result['type'] == 'progress':
                    print(result['log']['message'])
                    self.message = result['log']['message']

                if result['type'] == 'failure':
                    self.report(type={'ERROR'}, message=result['reason'])
                    return {'CANCELLED'}

            except ValueError:
                pass
            except TypeError:
                pass
            except json.decoder.JSONDecodeError:
                pass
            
            self.rhubarb.poll()

            if self.rhubarb.returncode is not None:
                wm.event_timer_remove(self._timer)
    
                results = json.loads(stdout)
                fps = context.scene.render.fps
                lib = context.object.pose_library
                last_frame = 0
                prev_pose = 0

                for cue in results['mouthCues']:
                    frame_num = round(cue['start'] * fps) + lib.mouth_shapes.start_frame
                    
                    # add hold key if time since last key is large
                    if frame_num - last_frame > self.hold_frame_threshold:
                        print("hold frame: {0}".format(frame_num- self.hold_frame_threshold))
                        bpy.ops.poselib.apply_pose(pose_index=prev_pose)
                        self.set_keyframes(context, frame_num - self.hold_frame_threshold)

                    print("start: {0} frame: {1} value: {2}".format(cue['start'], frame_num , cue['value']))

                    mouth_shape = 'mouth_' + cue['value'].lower()
                    if mouth_shape in context.object.pose_library.mouth_shapes:
                        pose_index = context.object.pose_library.mouth_shapes[mouth_shape]
                    else:
                        pose_index = 0

                    bpy.ops.poselib.apply_pose(pose_index=pose_index)
                    self.set_keyframes(context, frame_num)
                    

                    prev_pose = pose_index
                    last_frame = frame_num
                    wm.progress_end()
                return {'FINISHED'}

            return {'PASS_THROUGH'}
        except subprocess.TimeoutExpired as ex:
            return {'PASS_THROUGH'}
        except json.decoder.JSONDecodeError:
            print(stdout)
            print("Error!!!")
            wm.progress_end()
            return {'CANCELLED'}
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r}"
            print(template.format(type(ex).__name__, ex.args))
            wm.progress_end()
            return {'CANCELLED'}

    def set_keyframes(self, context, frame):
        for bone in context.selected_pose_bones:
            bone.keyframe_insert(data_path='location', frame=frame)
            if bone.rotation_mode == 'QUATERNION':
                bone.keyframe_insert(data_path='rotation_quaternion', frame=frame)
            else:
                bone.keyframe_insert(data_path='rotation_euler', frame=frame)
            bone.keyframe_insert(data_path='scale', frame=frame)

    def invoke(self, context, event):
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences

        inputfile = bpy.path.abspath(context.object.pose_library.mouth_shapes.sound_file)
        dialogfile = bpy.path.abspath(context.object.pose_library.mouth_shapes.dialog_file)
        recognizer = bpy.path.abspath(addon_prefs.recognizer)
        executable = bpy.path.abspath(addon_prefs.executable_path)
        
        # This is ugly, but Blender unpacks the zip without execute permission
        os.chmod(executable, 0o744)

        command = [executable, "-f", "json", "--machineReadable", "--extendedShapes", "GHX", "-r", recognizer, inputfile]
        
        if dialogfile:
            command.append("--dialogFile")
            command.append(dialogfile )
        
        self.rhubarb = subprocess.Popen(command,
                                        stdout=subprocess.PIPE, universal_newlines=True)

        wm = context.window_manager
        self._timer = wm.event_timer_add(2, window=context.window)

        wm.modal_handler_add(self)

        wm.progress_begin(0, 100)

        return {'RUNNING_MODAL'}

    def execute(self, context):
        return self.invoke(context, None)

    def finished(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)



class RhubarbLipsyncPencilOperator(bpy.types.Operator):
    """Run Rhubarb lipsync"""
    bl_idname = "object.rhubarb_pencil_lipsync"
    bl_label = "Rhubarb lipsync for Grease Pencil"

    cue_prefix = 'Mouth_'
    hold_frame_threshold = 4

    @classmethod
    def poll(cls, context):
        return context.preferences.addons[__package__].preferences.executable_path # and \
            # context.object.data.layers and \
            # context.object.data.mouth_shapes.sound_file

    def modal(self, context, event):
        wm = context.window_manager
        wm.progress_update(50)

        try:
            (stdout, stderr) = self.rhubarb.communicate(timeout=1)

            try:
                result = json.loads(stderr)
                if result['type'] == 'progress':
                    print(result['log']['message'])
                    self.message = result['log']['message']

                if result['type'] == 'failure':
                    self.report(type={'ERROR'}, message=result['reason'])
                    return {'CANCELLED'}

            except ValueError:
                pass
            except TypeError:
                pass
            except json.decoder.JSONDecodeError:
                pass

            self.rhubarb.poll()

            if self.rhubarb.returncode is not None:
                wm.event_timer_remove(self._timer)

                results = json.loads(stdout)
                fps = context.scene.render.fps
                lib = context.object.data
                last_frame = 0

                for cue in results['mouthCues']:
                    frame_num = round(cue['start'] * fps) + lib.mouth_shapes.start_frame

                    for layer in context.object.data.mouth_shapes.values():
                        try:
                            lib.layers[layer].hide = True
                        except:
                            print("Skipping {} index out of range".format(layer))

                    mouth_shape = 'mouth_' + cue['value'].lower()
                    if mouth_shape in lib.mouth_shapes.keys():
                        lib.layers[lib.mouth_shapes[mouth_shape]].hide = False


                    self.set_keyframes(context, frame_num)
                    wm.progress_end()

                    print("frame {}: {}".format(frame_num, mouth_shape))
                return {'FINISHED'}

            return {'PASS_THROUGH'}
        except subprocess.TimeoutExpired as ex:
            return {'PASS_THROUGH'}
        except json.decoder.JSONDecodeError:
            print(stdout)
            print("Error!!!")
            wm.progress_end()
            return {'CANCELLED'}
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r}"
            print(template.format(type(ex).__name__, ex.args))
            wm.progress_end()
            return {'CANCELLED'}

    def set_keyframes(self, context, frame):
        for layer_index in context.object.data.mouth_shapes.keys():
            try:
                layer = context.object.data.layers[context.object.data.mouth_shapes[layer_index]]
                layer.keyframe_insert(data_path='hide', frame=frame)
            except:
                print("Skipping {} not a layer".format(layer_index))


    def invoke(self, context, event):
        preferences = context.preferences
        addon_prefs = preferences.addons[__package__].preferences

        inputfile = bpy.path.abspath(context.object.data.mouth_shapes.sound_file)
        dialogfile = bpy.path.abspath(context.object.data.mouth_shapes.dialog_file)
        recognizer = bpy.path.abspath(addon_prefs.recognizer)
        executable = bpy.path.abspath(addon_prefs.executable_path)

        # This is ugly, but Blender unpacks the zip without execute permission
        os.chmod(executable, 0o744)

        command = [executable, "-f", "json", "--machineReadable", "--extendedShapes", "GHX", "-r", recognizer, inputfile]

        if dialogfile:
            command.append("--dialogFile")
            command.append(dialogfile )

        self.rhubarb = subprocess.Popen(command,
                                        stdout=subprocess.PIPE, universal_newlines=True)

        wm = context.window_manager
        self._timer = wm.event_timer_add(2, window=context.window)

        wm.modal_handler_add(self)

        wm.progress_begin(0, 100)

        return {'RUNNING_MODAL'}

    def execute(self, context):
        return self.invoke(context, None)

    def finished(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)


def register():
    bpy.utils.register_class(RhubarbLipsyncOperator)
    bpy.utils.register_class(RhubarbLipsyncPencilOperator)


def unregister():
    bpy.utils.unregister_class(RhubarbLipsyncOperator)
    bpy.utils.unregister_class(RhubarbLipsyncPencilOperator)

if __name__ == "__main__":
    register()

