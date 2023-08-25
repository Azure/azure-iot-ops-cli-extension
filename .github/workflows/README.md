### Template / automated actions:
	azdev_linter.yml
	ci_build.yml
	security_checks.yml
	smoke_test.yml
	stage_release.yml
	update_private_index.yml
	upload_wheel.yml

### Top-level / triggered workflows:
 - CI Build and Test (ci_workflow)

 - CodeQL 

 - Build Wheel for Release (release_build.yml)
   - Inputs   
     - upload_wheel: bool
   - Tasks
     - Build
     - if (upload_wheel) - run upload_wheel.yml

 - Build and Publish Release (release_workflow)
   - Inputs
     - continue_on_fail: bool
     - update_index: bool
   - Tasks
     - security
     - (release_build.yml - upload_wheel: false)
     - tox
     - azdev_linter
     - smoke_test
     - stage_release (update_index: true)
       - if update_index:
         - stage_release.yml
            - Draft Github Release
            - upload_wheel.yml
            - update_private_index.yml